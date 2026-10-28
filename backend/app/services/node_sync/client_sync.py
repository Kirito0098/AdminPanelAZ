"""Auto-sync VPN clients from primary to replicas in a sync group."""

from __future__ import annotations

import logging
import threading
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import BackgroundTask, Node, VpnConfig, VpnType
from app.services.access_policy import forget_deleted_openvpn_client
from app.services.background_tasks import background_task_service
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.groups import (
    find_sync_group_for_primary,
    get_replica_nodes,
    is_auto_sync_enabled,
)
from app.services.node_sync.manual_link import link_primary_config_to_group
from app.services.node_sync.replicate import (
    ReplicateOperation,
    get_shadow_configs,
    replicate_to_replicas,
)
from app.services.node_sync.vpn_state_sync import (
    ReplicaRuntimeError,
    replicate_primary_crypto_to_replicas,
    sync_vpn_crypto_from_primary,
)

logger = logging.getLogger(__name__)

HA_CLIENT_SYNC_TASK = "ha_client_sync"

_ha_group_locks: dict[int, threading.Lock] = {}
_ha_group_locks_guard = threading.Lock()


def ha_group_lock(group_id: int) -> threading.Lock:
    """Serialize HA crypto ops (client sync, AWG2 overlay) per sync group."""
    with _ha_group_locks_guard:
        lock = _ha_group_locks.get(group_id)
        if lock is None:
            lock = threading.Lock()
            _ha_group_locks[group_id] = lock
        return lock


def _ha_group_lock(group_id: int) -> threading.Lock:
    return ha_group_lock(group_id)


def format_ha_replicate_errors(result: dict[str, Any] | None) -> str | None:
    if not result:
        return None
    errors = result.get("errors") or []
    if not errors:
        return None
    nodes = ", ".join(str(entry.get("node_name") or entry.get("node_id") or "?") for entry in errors)
    first_error = str(errors[0].get("error") or "неизвестная ошибка")
    return f"Не удалось синхронизировать VPN-ключи на реплику ({nodes}): {first_error}"


def replicate_client_create(
    db: Session,
    group,
    primary_config: VpnConfig,
) -> dict[str, Any]:
    """Create matching client on all replicas and linked VpnConfig rows."""
    result = replicate_to_replicas(
        db,
        group,
        ReplicateOperation.CLIENT_CREATE,
        {"primary_config": primary_config},
    )
    return result.to_legacy_dict()


def replicate_client_delete(
    db: Session,
    group,
    primary_config: VpnConfig,
) -> dict[str, Any]:
    """Delete client from replicas and remove shadow VpnConfig rows."""
    result = replicate_to_replicas(
        db,
        group,
        ReplicateOperation.CLIENT_DELETE,
        {"primary_config": primary_config},
    )
    return result.to_legacy_dict()


def purge_ha_shadow_configs(db: Session, primary_config_id: int) -> int:
    """Remove replica VpnConfig rows pointing at a primary (FK safety before primary delete)."""
    return (
        db.query(VpnConfig)
        .filter(VpnConfig.ha_primary_config_id == primary_config_id)
        .delete(synchronize_session=False)
    )


def maybe_replicate_config_metadata(
    db: Session,
    *,
    node_id: int,
    primary_config: VpnConfig,
) -> dict[str, Any] | None:
    group = find_sync_group_for_primary(db, node_id)
    if not group or not is_auto_sync_enabled(group):
        return None
    result = replicate_to_replicas(
        db,
        group,
        ReplicateOperation.CLIENT_METADATA_PATCH,
        {"primary_config": primary_config},
    )
    return result.to_legacy_dict()


def _enqueue_ha_client_sync(
    *,
    group_id: int,
    op: str,
    created_by_username: str | None,
    queued_message: str,
    payload: dict[str, Any],
) -> BackgroundTask:
    subject_key = f"ha-group:{group_id}"

    def _callable(progress_updater=None) -> dict[str, Any]:
        with _ha_group_lock(group_id):
            if progress_updater:
                progress_updater(20, f"HA sync ({op})…")
            return _run_ha_client_sync_payload(payload)

    return background_task_service.enqueue_background_task(
        HA_CLIENT_SYNC_TASK,
        _callable,
        created_by_username=created_by_username,
        queued_message=queued_message,
        subject_key=subject_key,
    )


def _run_ha_client_sync_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from app.models import NodeSyncGroup

    op = str(payload.get("op") or "")
    group_id = int(payload["group_id"])
    db = SessionLocal()
    try:
        group = db.get(NodeSyncGroup, group_id)
        if not group:
            raise RuntimeError(f"HA-группа {group_id} не найдена")

        if op == "create":
            config = db.get(VpnConfig, int(payload["primary_config_id"]))
            if not config:
                raise RuntimeError("Конфиг для HA create не найден")
            if is_auto_sync_enabled(group):
                result = replicate_client_create(db, group, config)
            else:
                crypto = replicate_primary_crypto_to_replicas(db, group, config)
                link_primary_config_to_group(db, group, config)
                result = {
                    "replicated": crypto.get("successes") or [],
                    "errors": crypto.get("errors") or [],
                    "linked": True,
                    "crypto": crypto,
                }
            db.commit()
            errors = result.get("errors") or []
            if errors:
                raise RuntimeError(format_ha_replicate_errors(result) or "HA create sync failed")
            return {"ok": True, "op": op, "result": result}

        if op == "renew_cert":
            config = db.get(VpnConfig, int(payload["primary_config_id"]))
            if not config:
                raise RuntimeError("Конфиг для HA renew не найден")
            cert_expire_days = int(payload["cert_expire_days"])
            if is_auto_sync_enabled(group):
                result = replicate_to_replicas(
                    db,
                    group,
                    ReplicateOperation.CLIENT_RENEW_CERT,
                    {"primary_config": config, "cert_expire_days": cert_expire_days},
                ).to_legacy_dict()
            else:
                if config.vpn_type != VpnType.openvpn:
                    return {"ok": True, "op": op, "skipped": True}
                crypto = replicate_primary_crypto_to_replicas(db, group, config)
                for shadow in get_shadow_configs(db, group, config):
                    shadow.cert_expire_days = cert_expire_days
                    shadow.cert_expires_at = config.cert_expires_at
                result = {
                    "successes": crypto.get("successes") or [],
                    "errors": crypto.get("errors") or [],
                    "crypto": crypto,
                }
            db.commit()
            errors = result.get("errors") or []
            if errors:
                raise RuntimeError(format_ha_replicate_errors(result) or "HA renew sync failed")
            return {"ok": True, "op": op, "result": result}

        if op == "delete":
            # Primary DB row / shadows may already be gone; sync disk state to replicas.
            result = _sync_delete_to_replicas_disk(
                db,
                group,
                node_id=int(payload["node_id"]),
                client_name=str(payload["client_name"]),
                vpn_type=VpnType(str(payload["vpn_type"])),
            )
            db.commit()
            errors = result.get("errors") or []
            if errors:
                raise RuntimeError(format_ha_replicate_errors(result) or "HA delete sync failed")
            return {"ok": True, "op": op, "result": result}

        raise RuntimeError(f"Неизвестная HA sync операция: {op}")
    finally:
        db.close()


def _sync_delete_to_replicas_disk(
    db: Session,
    group,
    *,
    node_id: int,
    client_name: str,
    vpn_type: VpnType,
) -> dict[str, Any]:
    """After primary disk delete (+ DB purge), push crypto state to replicas."""
    primary_node = db.get(Node, node_id)
    if not primary_node:
        raise RuntimeError(f"Primary node {node_id} не найден")
    primary_adapter = get_adapter_for_node(primary_node)
    successes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for replica_node in get_replica_nodes(db, group):
        try:
            replica_adapter = get_adapter_for_node(replica_node)
            sync_vpn_crypto_from_primary(
                primary_adapter,
                replica_adapter,
                vpn_type,
                db=db,
                replica_node=replica_node,
                client_name=client_name if vpn_type != VpnType.openvpn else None,
            )
            if vpn_type == VpnType.openvpn:
                forget_deleted_openvpn_client(
                    db, replica_adapter, node_id=replica_node.id, client_name=client_name
                )
            successes.append({"node_id": replica_node.id, "node_name": replica_node.name})
        except ReplicaRuntimeError as exc:
            logger.warning(
                "HA async delete: runtime drift on replica %s: %s",
                replica_node.name,
                exc,
            )
            successes.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "drift": str(exc)}
            )
        except Exception as exc:
            logger.warning(
                "HA async delete failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)}
            )
    return {"deleted": successes, "errors": errors, "successes": successes}


def enqueue_maybe_replicate_create(
    db: Session,
    *,
    node_id: int,
    primary_config: VpnConfig,
    created_by_username: str | None = None,
) -> dict[str, Any] | None:
    """Queue HA create sync; returns ``{task_id}`` or None when node is not an HA primary."""
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    if not is_auto_sync_enabled(group):
        link_primary_config_to_group(db, group, primary_config)
        db.flush()
    task = _enqueue_ha_client_sync(
        group_id=group.id,
        op="create",
        created_by_username=created_by_username,
        queued_message=f"HA sync: создание «{primary_config.client_name}»…",
        payload={
            "op": "create",
            "group_id": group.id,
            "primary_config_id": primary_config.id,
        },
    )
    return {"task_id": task.id, "queued": True}


def enqueue_maybe_replicate_delete(
    db: Session,
    *,
    node_id: int,
    primary_config: VpnConfig,
    created_by_username: str | None = None,
) -> dict[str, Any] | None:
    """Queue HA delete disk sync. Caller still purges shadow rows and deletes primary."""
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    task = _enqueue_ha_client_sync(
        group_id=group.id,
        op="delete",
        created_by_username=created_by_username,
        queued_message=f"HA sync: удаление «{primary_config.client_name}»…",
        payload={
            "op": "delete",
            "group_id": group.id,
            "node_id": node_id,
            "client_name": primary_config.client_name,
            "vpn_type": primary_config.vpn_type.value,
        },
    )
    return {"task_id": task.id, "queued": True}


def enqueue_maybe_replicate_cert_renew(
    db: Session,
    *,
    node_id: int,
    primary_config: VpnConfig,
    cert_expire_days: int,
    created_by_username: str | None = None,
) -> dict[str, Any] | None:
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    task = _enqueue_ha_client_sync(
        group_id=group.id,
        op="renew_cert",
        created_by_username=created_by_username,
        queued_message=f"HA sync: продление «{primary_config.client_name}»…",
        payload={
            "op": "renew_cert",
            "group_id": group.id,
            "primary_config_id": primary_config.id,
            "cert_expire_days": cert_expire_days,
        },
    )
    return {"task_id": task.id, "queued": True}


# Sync wrappers kept for tests / callers that still need in-process replicate.
def maybe_replicate_create(db: Session, *, node_id: int, primary_config: VpnConfig) -> dict[str, Any] | None:
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    if is_auto_sync_enabled(group):
        return replicate_client_create(db, group, primary_config)

    crypto = replicate_primary_crypto_to_replicas(db, group, primary_config)
    link_primary_config_to_group(db, group, primary_config)
    return {
        "replicated": crypto.get("successes") or [],
        "errors": crypto.get("errors") or [],
        "skipped": False,
        "linked": True,
        "crypto": crypto,
    }


def maybe_replicate_delete(db: Session, *, node_id: int, primary_config: VpnConfig) -> dict[str, Any] | None:
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    if is_auto_sync_enabled(group):
        result = replicate_client_delete(db, group, primary_config)
        if not (result.get("deleted") or result.get("errors")):
            crypto = replicate_primary_crypto_to_replicas(db, group, primary_config)
            return {
                "deleted": crypto.get("successes") or [],
                "errors": crypto.get("errors") or [],
                "skipped": False,
                "crypto": crypto,
                "fallback": True,
            }
        return result

    crypto = replicate_primary_crypto_to_replicas(db, group, primary_config)
    return {
        "deleted": crypto.get("successes") or [],
        "errors": crypto.get("errors") or [],
        "skipped": False,
        "crypto": crypto,
    }


def maybe_replicate_cert_renew(
    db: Session,
    *,
    node_id: int,
    primary_config: VpnConfig,
    cert_expire_days: int,
) -> dict[str, Any] | None:
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    if is_auto_sync_enabled(group):
        result = replicate_to_replicas(
            db,
            group,
            ReplicateOperation.CLIENT_RENEW_CERT,
            {"primary_config": primary_config, "cert_expire_days": cert_expire_days},
        )
        return result.to_legacy_dict()

    if primary_config.vpn_type.value != "openvpn":
        return None
    crypto = replicate_primary_crypto_to_replicas(db, group, primary_config)
    for shadow in get_shadow_configs(db, group, primary_config):
        shadow.cert_expire_days = cert_expire_days
        shadow.cert_expires_at = primary_config.cert_expires_at
    db.flush()
    return {"successes": crypto.get("successes") or [], "errors": crypto.get("errors") or [], "crypto": crypto}
