"""HA auto-sync for runtime client operations (primary → replicas)."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node, NodeSyncGroup
from app.services.access_policy import (
    AccessPolicyService,
    clear_cooldown_ban,
    register_cooldown_ban,
)
from app.services.node_manager import get_adapter_for_node, node_metadata_dict
from app.services.node_sync.groups import find_sync_group_for_primary, is_auto_sync_enabled
from app.services.node_sync.replicate import (
    ReplicateOperation,
    ReplicateResult,
    finalize_replicate_outcome,
    iter_replica_adapters,
)

logger = logging.getLogger(__name__)
settings = get_settings()

_NOT_CONNECTED_MARKERS = ("не найден", "not connected", "not found")


def _antizapret_path_for_node(node: Node) -> Path:
    meta = node_metadata_dict(node)
    raw = meta.get("antizapret_path")
    return Path(str(raw)) if raw else settings.antizapret_path


def _policy_service(db: Session, node: Node, adapter) -> AccessPolicyService:
    return AccessPolicyService(
        db,
        antizapret_path=_antizapret_path_for_node(node),
        node_id=node.id,
        node_name=node.name,
        adapter=adapter,
    )


def schedule_disconnect_cooldown_release(
    node_id: int,
    client_name: str,
    *,
    cooldown_seconds: int,
) -> None:
    """Lift the transient disconnect ban on one node after the cooldown window."""

    def _worker() -> None:
        time.sleep(max(0, int(cooldown_seconds)))
        clear_cooldown_ban(node_id, client_name)
        db = SessionLocal()
        try:
            node = db.get(Node, node_id)
            if node is None:
                return
            svc = _policy_service(db, node, get_adapter_for_node(node))
            svc.reconcile_openvpn(client_name)
        except Exception:
            logger.exception(
                "disconnect cooldown release failed for %s on node %s",
                client_name,
                node_id,
            )
        finally:
            db.close()

    threading.Thread(
        target=_worker,
        name=f"ovpn-cooldown-{node_id}-{client_name}",
        daemon=True,
    ).start()


def apply_openvpn_disconnect_on_node(
    db: Session,
    node: Node,
    client_name: str,
    *,
    cooldown_seconds: int = 0,
    keep_cooldown_if_not_connected: bool = False,
) -> dict:
    """Briefly ban (optional), kill the session, and return the disconnect result."""
    client_name = client_name.strip()
    adapter = get_adapter_for_node(node)
    svc = _policy_service(db, node, adapter)
    cooldown = max(0, int(cooldown_seconds))

    if cooldown > 0:
        register_cooldown_ban(node.id, client_name, cooldown)
        svc.reconcile_openvpn(client_name)

    try:
        result = adapter.disconnect_openvpn_client(client_name)
    except Exception:
        if cooldown > 0:
            clear_cooldown_ban(node.id, client_name)
            svc.reconcile_openvpn(client_name)
        raise

    if not result.get("success"):
        if cooldown > 0:
            if keep_cooldown_if_not_connected and _is_disconnect_skip_not_connected(result):
                schedule_disconnect_cooldown_release(
                    node.id,
                    client_name,
                    cooldown_seconds=cooldown,
                )
                result["cooldown_seconds"] = cooldown
            else:
                clear_cooldown_ban(node.id, client_name)
                svc.reconcile_openvpn(client_name)
        return result

    if cooldown > 0:
        schedule_disconnect_cooldown_release(
            node.id,
            client_name,
            cooldown_seconds=cooldown,
        )
        result["cooldown_seconds"] = cooldown

    return result


def _is_disconnect_skip_not_connected(result: dict) -> bool:
    if result.get("success"):
        return False
    message = str(result.get("message", "")).lower()
    return any(marker in message for marker in _NOT_CONNECTED_MARKERS)


def replicate_openvpn_disconnect(
    db: Session,
    group: NodeSyncGroup,
    client_name: str,
    *,
    cooldown_seconds: int = 0,
) -> ReplicateResult:
    """Best-effort disconnect of the same client on all replicas."""
    result = ReplicateResult(operation=ReplicateOperation.OPENVPN_DISCONNECT)
    if not is_auto_sync_enabled(group):
        result.skipped = True
        return result

    client_name = client_name.strip()
    for replica_node, _adapter in iter_replica_adapters(db, group):
        try:
            disconnect_result = apply_openvpn_disconnect_on_node(
                db,
                replica_node,
                client_name,
                cooldown_seconds=cooldown_seconds,
                keep_cooldown_if_not_connected=True,
            )
        except Exception as exc:
            logger.warning(
                "HA openvpn disconnect failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)}
            )
            continue

        if disconnect_result.get("success"):
            result.successes.append({"node_id": replica_node.id})
            continue

        if _is_disconnect_skip_not_connected(disconnect_result):
            entry: dict[str, Any] = {
                "node_id": replica_node.id,
                "skipped": True,
                "note": "client_not_connected",
            }
            if disconnect_result.get("cooldown_seconds"):
                entry["cooldown_applied"] = True
            result.successes.append(entry)
            continue

        message = str(disconnect_result.get("message", "disconnect failed"))
        logger.warning(
            "HA openvpn disconnect failed on replica %s: %s",
            replica_node.name,
            message,
        )
        result.errors.append(
            {"node_id": replica_node.id, "node_name": replica_node.name, "error": message}
        )

    finalize_replicate_outcome(
        db,
        group,
        result,
        payload={"client_name": client_name, "cooldown_seconds": cooldown_seconds},
        set_synced_on_success=True,
        audit_on_partial_failure=True,
    )
    return result


def maybe_replicate_openvpn_disconnect(
    db: Session,
    *,
    node_id: int,
    client_name: str,
    cooldown_seconds: int = 0,
) -> dict[str, Any] | None:
    """Replicate OpenVPN disconnect to HA replicas when active node is primary in auto sync group."""
    group = find_sync_group_for_primary(db, node_id)
    if not group or not is_auto_sync_enabled(group):
        return None
    result = replicate_openvpn_disconnect(
        db,
        group,
        client_name,
        cooldown_seconds=cooldown_seconds,
    )
    return {
        "applied": result.successes,
        "errors": result.errors,
        "skipped": result.skipped,
    }
