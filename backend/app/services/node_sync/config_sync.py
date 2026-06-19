"""HA auto-sync for AntiZapret config files (primary → replicas)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import NodeSyncGroup
from app.services.edit_files_transfer import run_edit_files_transfer
from app.services.file_editor import EDITABLE_FILES
from app.services.node_sync.fingerprints import CONFIG_FINGERPRINT_EXCLUDE
from app.services.node_sync.groups import find_sync_group_for_primary, get_replica_nodes, is_auto_sync_enabled
from app.services.node_sync.replicate import ReplicateOperation, ReplicateResult, finalize_replicate_outcome

logger = logging.getLogger(__name__)


def _is_excluded_file_key(key: str) -> bool:
    fname = EDITABLE_FILES.get(key)
    return bool(fname and fname in CONFIG_FINGERPRINT_EXCLUDE)


def _filter_replicable_file_keys(file_keys: list[str]) -> tuple[list[str], list[str]]:
    """Return (keys_to_transfer, excluded_keys) preserving order without duplicates."""
    replicable: list[str] = []
    excluded: list[str] = []
    seen: set[str] = set()
    for key in file_keys:
        if key in seen:
            continue
        seen.add(key)
        if _is_excluded_file_key(key):
            excluded.append(key)
        else:
            replicable.append(key)
    return replicable, excluded


def _filter_content_overrides(content_overrides: dict[str, str] | None) -> dict[str, str] | None:
    if not content_overrides:
        return None
    filtered = {key: value for key, value in content_overrides.items() if not _is_excluded_file_key(key)}
    return filtered or None


def _transfer_result_to_replicate_result(transfer: dict[str, Any]) -> ReplicateResult:
    result = ReplicateResult(operation=ReplicateOperation.CONFIG_FILES_WRITE)
    for entry in transfer.get("per_node") or []:
        status = entry.get("status")
        if status == "success":
            result.successes.append(
                {
                    "node_id": entry["node_id"],
                    "node_name": entry.get("node_name"),
                    "transferred_files": entry.get("transferred_files") or [],
                }
            )
        elif status == "failed":
            result.errors.append(
                {
                    "node_id": entry["node_id"],
                    "node_name": entry.get("node_name"),
                    "error": entry.get("error") or "transfer failed",
                }
            )
    return result


def replicate_config_files(
    db: Session,
    group: NodeSyncGroup,
    file_keys: list[str],
    *,
    run_doall: bool = False,
    content_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Replicate config file writes from primary to HA group replicas only."""
    replicable_keys, excluded_keys = _filter_replicable_file_keys(file_keys)
    filtered_overrides = _filter_content_overrides(content_overrides)

    if not is_auto_sync_enabled(group):
        return {
            "skipped": True,
            "success": False,
            "replicated": [],
            "errors": [],
            "excluded_file_keys": excluded_keys,
        }

    replica_nodes = get_replica_nodes(db, group)
    if not replica_nodes:
        result = ReplicateResult(operation=ReplicateOperation.CONFIG_FILES_WRITE)
        finalize_replicate_outcome(
            db,
            group,
            result,
            payload={"file_keys": file_keys},
            set_synced_on_success=True,
        )
        return {
            "skipped": False,
            "success": True,
            "replicated": [],
            "errors": [],
            "excluded_file_keys": excluded_keys,
        }

    if not replicable_keys:
        result = ReplicateResult(operation=ReplicateOperation.CONFIG_FILES_WRITE)
        finalize_replicate_outcome(
            db,
            group,
            result,
            payload={"file_keys": file_keys},
            set_synced_on_success=True,
        )
        return {
            "skipped": False,
            "success": True,
            "replicated": [],
            "errors": [],
            "excluded_file_keys": excluded_keys,
        }

    transfer = run_edit_files_transfer(
        db,
        file_keys=replicable_keys,
        target_node_ids=[node.id for node in replica_nodes],
        source_node_id=group.primary_node_id,
        run_doall=run_doall,
        content_overrides=filtered_overrides,
    )
    result = _transfer_result_to_replicate_result(transfer)
    finalize_replicate_outcome(
        db,
        group,
        result,
        payload={"file_keys": file_keys},
        set_synced_on_success=True,
        audit_on_partial_failure=False,
    )
    return {
        "skipped": False,
        "success": bool(transfer.get("success")),
        "replicated": result.successes,
        "errors": result.errors,
        "excluded_file_keys": excluded_keys,
        "transfer": transfer,
    }


def heal_config_drift(db: Session, group: NodeSyncGroup) -> dict[str, Any]:
    """Incremental reconcile heal: replicate all editable config files primary → replicas."""
    file_keys = list(EDITABLE_FILES.keys())
    run_doall = get_settings().node_sync_replicate_doall
    return replicate_config_files(db, group, file_keys, run_doall=run_doall)


def maybe_replicate_config_files(
    db: Session,
    *,
    node_id: int,
    file_keys: list[str],
    run_doall: bool = False,
    content_overrides: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Replicate config files when HA auto-sync and feature flag are enabled."""
    if not get_settings().node_sync_auto_replicate_config_files:
        return None
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    effective_doall = run_doall and get_settings().node_sync_replicate_doall
    return replicate_config_files(
        db,
        group,
        file_keys,
        run_doall=effective_doall,
        content_overrides=content_overrides,
    )
