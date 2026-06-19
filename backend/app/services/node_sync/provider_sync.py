"""HA auto-sync for CIDR provider list files (primary → replicas)."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.models import NodeSyncGroup
from app.services.cidr.constants import IP_FILES
from app.services.cidr.pipeline.constants import LIST_DIR
from app.services.cidr.pipeline.orchestrator import run_multi_deploy
from app.services.node_adapter import NodeAdapter
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.groups import get_replica_nodes, is_auto_sync_enabled
from app.services.node_sync.replicate import ReplicateOperation, ReplicateResult, finalize_replicate_outcome

logger = logging.getLogger(__name__)


def _filenames_to_deploy(primary_adapter: NodeAdapter) -> list[str]:
    overview = primary_adapter.get_routing_overview()
    providers = overview.get("providers") or []
    return [
        str(item["filename"])
        for item in providers
        if item.get("enabled")
        and item.get("has_source")
        and str(item.get("filename") or "") in IP_FILES
    ]


def _stage_primary_list_files(primary_adapter: NodeAdapter, filenames: list[str]) -> list[str]:
    """Copy enabled provider list files from primary into controller LIST_DIR for deploy."""
    os.makedirs(LIST_DIR, exist_ok=True)
    staged: list[str] = []
    for filename in filenames:
        try:
            data = primary_adapter.get_provider_content(filename)
            content = data.get("content", "")
        except Exception as exc:
            logger.warning("HA provider deploy: skip staging %s: %s", filename, exc)
            continue
        path = os.path.join(LIST_DIR, filename)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        staged.append(filename)
    return staged


def _deploy_result_to_replicate_result(deploy: dict[str, Any]) -> ReplicateResult:
    result = ReplicateResult(operation=ReplicateOperation.CIDR_DEPLOY_FILES)
    for entry in deploy.get("per_node") or []:
        status = entry.get("status")
        node_payload = {
            "node_id": entry.get("node_id"),
            "node_name": entry.get("node_name"),
            "pushed_files": entry.get("pushed_files") or [],
        }
        if status == "success":
            result.successes.append(node_payload)
        elif status in {"failed", "skipped"}:
            result.errors.append(
                {
                    **node_payload,
                    "error": entry.get("error") or f"deploy {status}",
                }
            )
    return result


def deploy_compiled_providers_to_replicas(
    db: Session,
    group: NodeSyncGroup,
    primary_adapter: NodeAdapter,
    *,
    sync_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """After compile/sync on primary, deploy list files to HA replicas via CIDR deploy path."""
    del sync_result  # reserved for future selective deploy from sync metadata

    if not is_auto_sync_enabled(group):
        return {"skipped": True, "success": False, "deploy": None, "filenames": []}

    replica_nodes = get_replica_nodes(db, group)
    if not replica_nodes:
        result = ReplicateResult(operation=ReplicateOperation.CIDR_DEPLOY_FILES)
        finalize_replicate_outcome(
            db,
            group,
            result,
            payload={"filenames": []},
            set_synced_on_success=True,
        )
        return {"skipped": False, "success": True, "deploy": None, "filenames": []}

    filenames = _filenames_to_deploy(primary_adapter)
    staged = _stage_primary_list_files(primary_adapter, filenames)
    if not staged:
        result = ReplicateResult(operation=ReplicateOperation.CIDR_DEPLOY_FILES)
        finalize_replicate_outcome(
            db,
            group,
            result,
            payload={"filenames": []},
            set_synced_on_success=True,
        )
        return {"skipped": False, "success": True, "deploy": None, "filenames": []}

    deploy = run_multi_deploy(
        db,
        target_node_ids=[node.id for node in replica_nodes],
        files=staged,
        sync_after=True,
        apply_after=False,
        triggered_by="ha_routing_sync",
    )
    result = _deploy_result_to_replicate_result(deploy)
    finalize_replicate_outcome(
        db,
        group,
        result,
        payload={"filenames": staged},
        set_synced_on_success=True,
        audit_on_partial_failure=True,
    )
    return {
        "skipped": False,
        "success": bool(deploy.get("success")),
        "filenames": staged,
        "deploy": deploy,
    }


def replicate_provider_content(
    db: Session,
    group: NodeSyncGroup,
    filename: str,
    content: str,
) -> ReplicateResult:
    """Replicate a provider list file from primary to all HA group replicas."""
    result = ReplicateResult(operation=ReplicateOperation.CIDR_DEPLOY_FILES)

    if not is_auto_sync_enabled(group):
        result.skipped = True
        return result

    for replica_node in get_replica_nodes(db, group):
        adapter = get_adapter_for_node(replica_node)
        try:
            adapter.save_provider_content(filename, content)
        except Exception as exc:
            logger.warning(
                "HA provider sync failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)}
            )
            continue
        result.successes.append({"node_id": replica_node.id, "node_name": replica_node.name, "filename": filename})

    finalize_replicate_outcome(
        db,
        group,
        result,
        payload={"filename": filename},
        set_synced_on_success=True,
        audit_on_partial_failure=True,
    )
    return result
