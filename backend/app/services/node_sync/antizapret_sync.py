"""HA auto-sync for AntiZapret setup settings (primary → replicas)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import BackgroundTask, Node, NodeSyncGroup
from app.services.antizapret_params import filter_ha_replicable_settings
from app.services.background_tasks import background_task_service
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.groups import get_replica_nodes, is_auto_sync_enabled
from app.services.node_sync.replicate import ReplicateOperation, ReplicateResult, finalize_replicate_outcome

logger = logging.getLogger(__name__)


def replicate_antizapret_settings(
    db: Session,
    group: NodeSyncGroup,
    updates: dict[str, Any],
) -> ReplicateResult:
    """Replicate setup settings from primary to all HA group replicas."""
    filtered = filter_ha_replicable_settings(updates)
    result = ReplicateResult(operation=ReplicateOperation.ANTIZAPRET_SETTINGS_PATCH)

    if not is_auto_sync_enabled(group):
        result.skipped = True
        return result

    if not filtered:
        finalize_replicate_outcome(
            db,
            group,
            result,
            payload={"updates": updates, "filtered_updates": filtered},
            set_synced_on_success=True,
        )
        return result

    for replica_node in get_replica_nodes(db, group):
        adapter = get_adapter_for_node(replica_node)
        try:
            adapter.update_antizapret_settings(filtered)
        except Exception as exc:
            logger.warning(
                "HA antizapret settings sync failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)}
            )
            continue
        result.successes.append({"node_id": replica_node.id, "node_name": replica_node.name})

    finalize_replicate_outcome(
        db,
        group,
        result,
        payload={"updates": updates, "filtered_updates": filtered},
        set_synced_on_success=True,
        audit_on_partial_failure=True,
    )
    return result


def heal_antizapret_drift(db: Session, group: NodeSyncGroup) -> dict[str, Any]:
    """Incremental reconcile heal: replicate primary setup settings and enqueue apply on replicas."""
    if not is_auto_sync_enabled(group):
        return {"success": False, "skipped": True, "errors": [], "applied": []}

    primary_node = db.get(Node, group.primary_node_id)
    if primary_node is None:
        return {
            "success": False,
            "skipped": False,
            "errors": [{"error": f"Primary node {group.primary_node_id} not found"}],
            "applied": [],
        }

    try:
        primary_settings = get_adapter_for_node(primary_node).get_antizapret_settings()
    except Exception as exc:
        logger.warning("HA antizapret heal: failed to read primary settings: %s", exc)
        return {
            "success": False,
            "skipped": False,
            "errors": [{"error": str(exc)}],
            "applied": [],
        }

    replicate_result = replicate_antizapret_settings(db, group, primary_settings)
    if replicate_result.errors:
        return {
            "success": False,
            "skipped": False,
            "errors": replicate_result.errors,
            "applied": replicate_result.successes,
        }

    enqueue_ha_routing_apply_replicas(db, group, created_by_username="system")
    return {
        "success": True,
        "skipped": False,
        "errors": [],
        "applied": replicate_result.successes,
    }


def enqueue_ha_routing_apply_replicas(
    db: Session,
    group: NodeSyncGroup,
    *,
    created_by_username: str | None = None,
) -> list[BackgroundTask]:
    """Enqueue independent routing apply tasks for each HA replica (non-blocking)."""
    if not is_auto_sync_enabled(group):
        return []

    tasks = []
    for replica_node in get_replica_nodes(db, group):
        task = background_task_service.enqueue_background_task(
            "routing_apply_replica",
            background_task_service.make_routing_apply_for_node_callable(replica_node.id),
            created_by_username=created_by_username,
            queued_message=f"Применение маршрутизации на replica «{replica_node.name}»…",
        )
        tasks.append(task)
    return tasks
