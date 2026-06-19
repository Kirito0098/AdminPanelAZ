"""HA auto-sync for runtime client operations (primary → replicas)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import NodeSyncGroup
from app.services.node_sync.groups import find_sync_group_for_primary, is_auto_sync_enabled
from app.services.node_sync.replicate import (
    ReplicateOperation,
    ReplicateResult,
    finalize_replicate_outcome,
    iter_replica_adapters,
)

logger = logging.getLogger(__name__)

_NOT_CONNECTED_MARKERS = ("не найден", "not connected", "not found")


def _is_disconnect_skip_not_connected(result: dict) -> bool:
    if result.get("success"):
        return False
    message = str(result.get("message", "")).lower()
    return any(marker in message for marker in _NOT_CONNECTED_MARKERS)


def replicate_openvpn_disconnect(
    db: Session,
    group: NodeSyncGroup,
    client_name: str,
) -> ReplicateResult:
    """Best-effort disconnect of the same client on all replicas."""
    result = ReplicateResult(operation=ReplicateOperation.OPENVPN_DISCONNECT)
    if not is_auto_sync_enabled(group):
        result.skipped = True
        return result

    client_name = client_name.strip()
    for replica_node, adapter in iter_replica_adapters(db, group):
        try:
            disconnect_result = adapter.disconnect_openvpn_client(client_name)
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
            result.successes.append(
                {"node_id": replica_node.id, "skipped": True, "note": "client_not_connected"}
            )
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
        payload={"client_name": client_name},
        set_synced_on_success=True,
        audit_on_partial_failure=True,
    )
    return result


def maybe_replicate_openvpn_disconnect(
    db: Session,
    *,
    node_id: int,
    client_name: str,
) -> dict[str, Any] | None:
    """Replicate OpenVPN disconnect to HA replicas when active node is primary in auto sync group."""
    group = find_sync_group_for_primary(db, node_id)
    if not group or not is_auto_sync_enabled(group):
        return None
    result = replicate_openvpn_disconnect(db, group, client_name)
    return {
        "applied": result.successes,
        "errors": result.errors,
        "skipped": result.skipped,
    }
