"""Background queue: doall + HA config replicate, recreate profiles, AWG2 HA sync."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import BackgroundTask, Node
from app.services.background_tasks import background_task_service
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.config_sync import maybe_replicate_config_files
from app.services.node_sync.groups import find_sync_group_for_primary, get_replica_nodes
from app.services.node_sync.vpn_state_sync import sync_amneziawg2_state_from_primary
from app.services.openvpn_profile_repair import recreate_openvpn_profiles
from app.services.profile_delivery import load_node_remote_hosts

logger = logging.getLogger(__name__)

CONFIG_APPLY_TASK = "config_apply"
RECREATE_PROFILES_TASK = "recreate_profiles"
HA_AWG2_SYNC_TASK = "ha_awg2_sync"


def enqueue_doall_and_replicate(
    *,
    node_id: int,
    file_keys: list[str],
    content_overrides: dict[str, str] | None,
    created_by_username: str | None,
    run_doall: bool = True,
    run_replicate: bool = True,
    queued_message: str | None = None,
) -> BackgroundTask:
    """After files are already written on primary: doall (no client.sh 7) then HA replicate."""
    captured_keys = list(file_keys)
    captured_overrides = dict(content_overrides) if content_overrides else None
    captured_doall = bool(run_doall)
    captured_replicate = bool(run_replicate)
    captured_node_id = int(node_id)

    def _callable(progress_updater=None) -> dict[str, Any]:
        db = SessionLocal()
        try:
            node = db.get(Node, captured_node_id)
            if node is None:
                raise RuntimeError(f"Узел {captured_node_id} не найден")
            adapter = get_adapter_for_node(node)
            output = ""
            if captured_doall:
                if progress_updater:
                    progress_updater(15, f"{node.name}: doall.sh…")
                # Explicit False: edit/settings save must not drag in client.sh 7.
                result = background_task_service.task_run_doall(
                    adapter,
                    progress_updater,
                    recreate_profiles=False,
                    hosts=None,
                    ensure_openvpn_multihome=bool(node.openvpn_multihome),
                )
                output = str(result.get("output") or "")
            if captured_replicate and captured_keys:
                if progress_updater:
                    progress_updater(70, f"{node.name}: HA-репликация файлов…")
                maybe_replicate_config_files(
                    db,
                    node_id=captured_node_id,
                    file_keys=captured_keys,
                    run_doall=captured_doall,
                    content_overrides=captured_overrides,
                )
                db.commit()
            return {"ok": True, "output": output, "node_id": captured_node_id}
        finally:
            db.close()

    return background_task_service.enqueue_background_task(
        CONFIG_APPLY_TASK,
        _callable,
        created_by_username=created_by_username,
        queued_message=queued_message or "Применение конфигурации в фоне…",
        subject_key=f"node:{node_id}:config-apply",
    )


def enqueue_recreate_profiles(
    *,
    node_id: int,
    created_by_username: str | None,
) -> BackgroundTask:
    captured_node_id = int(node_id)

    def _callable(progress_updater=None) -> dict[str, Any]:
        db = SessionLocal()
        try:
            node = db.get(Node, captured_node_id)
            if node is None:
                raise RuntimeError(f"Узел {captured_node_id} не найден")
            if progress_updater:
                progress_updater(20, f"{node.name}: client.sh 7…")
            adapter = get_adapter_for_node(node)
            result = recreate_openvpn_profiles(
                adapter,
                hosts=load_node_remote_hosts(db, captured_node_id),
            )
            if not result.success:
                raise RuntimeError(
                    result.errors[0] if result.errors else "Ошибка пересоздания профилей"
                )
            return {"ok": True, "output": result.output or ""}
        finally:
            db.close()

    return background_task_service.enqueue_background_task(
        RECREATE_PROFILES_TASK,
        _callable,
        created_by_username=created_by_username,
        queued_message="Пересоздание профилей поставлено в очередь",
        subject_key=f"node:{node_id}:recreate-profiles",
    )


def run_ha_awg2_sync(db: Session, *, primary_node_id: int) -> dict[str, Any]:
    """Sync AWG2 overlay primary → replicas. Best-effort errors list (never raises)."""
    errors: list[dict[str, str | None]] = []
    try:
        group = find_sync_group_for_primary(db, primary_node_id)
        if not group:
            return {"attempted": False, "errors": []}
        primary = db.get(Node, primary_node_id)
        if primary is None:
            return {"attempted": True, "errors": [{"node_name": None, "error": "primary not found"}]}
        primary_adapter = get_adapter_for_node(primary)
        replicas = get_replica_nodes(db, group)
        if not replicas:
            return {"attempted": True, "errors": []}
        for replica in replicas:
            try:
                sync_amneziawg2_state_from_primary(
                    primary_adapter,
                    get_adapter_for_node(replica),
                    db=db,
                    replica_node=replica,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"node_name": replica.name, "error": str(exc)})
        return {"attempted": True, "errors": errors}
    except Exception as exc:  # noqa: BLE001
        logger.warning("HA AWG2 sync failed to start: %s", exc)
        return {"attempted": True, "errors": [{"node_name": None, "error": str(exc)}]}


def enqueue_ha_awg2_sync(
    *,
    primary_node_id: int,
    created_by_username: str | None = None,
) -> BackgroundTask | None:
    """Queue AWG2 HA push if node is HA primary; None when no sync group."""
    db = SessionLocal()
    try:
        group = find_sync_group_for_primary(db, primary_node_id)
        if not group:
            return None
        group_id = group.id
    finally:
        db.close()

    def _callable(progress_updater=None) -> dict[str, Any]:
        from app.services.node_sync.client_sync import ha_group_lock

        with ha_group_lock(group_id):
            if progress_updater:
                progress_updater(25, "HA AWG2 sync…")
            worker = SessionLocal()
            try:
                return run_ha_awg2_sync(worker, primary_node_id=primary_node_id)
            finally:
                worker.close()

    return background_task_service.enqueue_background_task(
        HA_AWG2_SYNC_TASK,
        _callable,
        created_by_username=created_by_username,
        queued_message="HA-синхронизация AZ-AWG2 в фоне…",
        subject_key=f"ha-group:{group_id}",
    )
