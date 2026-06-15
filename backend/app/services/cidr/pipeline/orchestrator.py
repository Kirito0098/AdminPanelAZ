"""CIDR pipeline orchestration: ingest → compile → deploy → apply."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Node, NodeStatus
from app.services.cidr.cidr_notify import (
    maybe_notify_deploy_failed,
    maybe_notify_ingest_partial,
    maybe_notify_rollback_failed,
)
from app.services.cidr.pipeline.deploy import compute_artifact_stamp, push_cidr_artifacts
from app.services.cidr.pipeline.db_pipeline import update_cidr_files_from_db
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService
from app.services.cidr.pipeline.file_pipeline import rollback_from_runtime_backup
from app.services.node_adapter import NodeAdapter, RemoteNodeAdapter
from app.services.node_manager import get_active_node, get_adapter_for_node

logger = logging.getLogger(__name__)


def run_ingest(
    db: Session,
    *,
    triggered_by: str = "cron",
    selected_files: list[str] | None = None,
    progress_callback=None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Download provider CIDRs into SQLite (ingest stage)."""
    svc = CidrDbUpdaterService(db=db)
    try:
        result = svc.refresh_all_providers(
            triggered_by=triggered_by,
            selected_files=selected_files,
            progress_callback=progress_callback,
            dry_run=dry_run,
        )
    finally:
        svc.close()
    maybe_notify_ingest_partial(db, result, triggered_by=triggered_by)
    return result


def run_compile(*, progress_callback=None, **kwargs) -> dict[str, Any]:
    """Generate CIDR list files from DB (compile stage)."""
    result = update_cidr_files_from_db(progress_callback=progress_callback, **kwargs)
    if result.get("success") or result.get("updated"):
        result["artifact_stamp"] = compute_artifact_stamp()
    return result


def run_deploy(adapter: NodeAdapter, files: list[str] | list[dict] | None = None) -> dict[str, Any]:
    """Deploy compiled artifacts to a node.

    Local adapter: sync list → config via ``sync_cidr_providers``.
    Remote adapter: push LIST_DIR artifacts, then sync on the node.
    """
    if isinstance(adapter, RemoteNodeAdapter):
        push_result = push_cidr_artifacts(adapter, filenames=files)
        sync_result = adapter.sync_cidr_providers()
        return {
            "mode": "remote",
            "pushed": push_result["pushed"],
            "failed": push_result["failed"],
            "skipped": push_result["skipped"],
            "sync": sync_result,
        }

    sync_result = adapter.sync_cidr_providers()
    return {"mode": "local", "sync": sync_result}


def run_apply(
    adapter: NodeAdapter,
    *,
    sync_after: bool = True,
    apply_after: bool = False,
) -> dict[str, Any]:
    """Sync CIDR providers and optionally run doall on the target node."""
    result: dict[str, Any] = {}
    if sync_after:
        result["sync"] = adapter.sync_cidr_providers()
    if apply_after:
        result["doall_output"] = adapter.apply_config_changes()
    return result


def resolve_deploy_targets(
    db: Session,
    *,
    target_node_ids: list[int] | None = None,
    all_online: bool = False,
    target_node_id: int | None = None,
) -> tuple[list[Node], list[dict[str, Any]]]:
    """Resolve nodes to deploy to; offline/missing nodes are returned as skipped entries."""
    skipped: list[dict[str, Any]] = []

    if all_online:
        nodes = db.query(Node).filter(Node.status == NodeStatus.online).order_by(Node.id).all()
        return nodes, skipped

    requested_ids: list[int] = []
    if target_node_ids:
        requested_ids = list(dict.fromkeys(target_node_ids))
    elif target_node_id is not None:
        requested_ids = [target_node_id]
    else:
        return [get_active_node(db)], skipped

    nodes: list[Node] = []
    for node_id in requested_ids:
        node = db.query(Node).filter(Node.id == node_id).first()
        if not node:
            skipped.append(
                {
                    "node_id": node_id,
                    "node_name": None,
                    "status": "skipped",
                    "pushed_files": [],
                    "failed": [],
                    "error": f"Узел {node_id} не найден",
                }
            )
            continue
        if node.status != NodeStatus.online:
            skipped.append(
                {
                    "node_id": node.id,
                    "node_name": node.name,
                    "status": "skipped",
                    "pushed_files": [],
                    "failed": [],
                    "error": "Узел offline",
                }
            )
            logger.info(
                "CIDR deploy: node %s (id=%s) offline — skipped, queued for manual retry",
                node.name,
                node.id,
            )
            continue
        nodes.append(node)
    return nodes, skipped


def _deploy_single_node(
    node: Node,
    adapter: NodeAdapter,
    *,
    files: list[str] | list[dict] | None,
    sync_after: bool,
    apply_after: bool,
) -> dict[str, Any]:
    """Push artifacts to one node, then optional sync/apply."""
    entry: dict[str, Any] = {
        "node_id": node.id,
        "node_name": node.name,
        "pushed_files": [],
        "failed": [],
    }
    try:
        deploy_result = run_deploy(adapter, files=files)
    except Exception as exc:
        entry["status"] = "failed"
        entry["error"] = str(exc)
        entry["failed"] = [{"file": "*", "error": str(exc)}]
        return entry

    failed = deploy_result.get("failed") or []
    pushed = deploy_result.get("pushed") or []
    entry["pushed_files"] = pushed
    entry["failed"] = failed
    if deploy_result.get("sync") is not None:
        entry["sync"] = deploy_result["sync"]

    if failed:
        entry["status"] = "failed"
        entry["error"] = f"Ошибка развёртывания: {len(failed)} файл(ов)"
        return entry

    if apply_after:
        apply_result = run_apply(adapter, sync_after=False, apply_after=True)
        entry.update(apply_result)
    elif sync_after:
        apply_result = run_apply(adapter, sync_after=not bool(pushed), apply_after=False)
        entry.update(apply_result)

    entry["status"] = "success"
    return entry


def run_multi_deploy(
    db: Session,
    *,
    target_node_ids: list[int] | None = None,
    all_online: bool = False,
    target_node_id: int | None = None,
    files: list[str] | list[dict] | None = None,
    sync_after: bool = True,
    apply_after: bool = False,
    triggered_by: str | None = None,
) -> dict[str, Any]:
    """Deploy CIDR artifacts to one or more nodes; offline nodes are skipped and logged."""
    nodes, skipped = resolve_deploy_targets(
        db,
        target_node_ids=target_node_ids,
        all_online=all_online,
        target_node_id=target_node_id,
    )
    per_node: list[dict[str, Any]] = list(skipped)
    all_pushed: list[str] = []
    all_failed: list[dict[str, str]] = []

    for node in nodes:
        try:
            adapter = get_adapter_for_node(node)
        except Exception as exc:
            per_node.append(
                {
                    "node_id": node.id,
                    "node_name": node.name,
                    "status": "failed",
                    "pushed_files": [],
                    "failed": [{"file": "*", "error": str(exc)}],
                    "error": str(exc),
                }
            )
            all_failed.append({"file": "*", "error": str(exc)})
            continue

        entry = _deploy_single_node(
            node,
            adapter,
            files=files,
            sync_after=sync_after,
            apply_after=apply_after,
        )
        per_node.append(entry)
        all_pushed.extend(entry.get("pushed_files") or [])
        all_failed.extend(entry.get("failed") or [])

    success_nodes = [e for e in per_node if e.get("status") == "success"]
    failed_nodes = [e for e in per_node if e.get("status") == "failed"]
    skipped_nodes = [e for e in per_node if e.get("status") == "skipped"]

    if failed_nodes:
        message = f"Развёртывание завершено с ошибками: {len(failed_nodes)} узел(ов)"
    elif skipped_nodes and not success_nodes:
        message = f"Нет online-узлов для развёртывания ({len(skipped_nodes)} пропущено)"
    else:
        pushed_total = len(all_pushed)
        node_count = len(success_nodes)
        message = f"Развёрнуто на {node_count} узел(ов), файлов: {pushed_total}"

    result = {
        "success": len(failed_nodes) == 0 and len(success_nodes) > 0,
        "message": message,
        "artifact_stamp": compute_artifact_stamp(),
        "per_node": per_node,
        "deploy": {
            "pushed": all_pushed,
            "failed": all_failed,
        },
        "nodes_deployed": len(success_nodes),
        "nodes_failed": len(failed_nodes),
        "nodes_skipped": len(skipped_nodes),
    }
    maybe_notify_deploy_failed(db, result, triggered_by=triggered_by)
    return result


def run_rollback(
    db: Session,
    backup_stamp: str,
    *,
    selected_files: list[str] | None = None,
    redeploy_after: bool = False,
    target_node_ids: list[int] | None = None,
    all_online: bool = False,
    target_node_id: int | None = None,
    sync_after: bool = True,
    apply_after: bool = False,
    triggered_by: str | None = None,
    progress_callback=None,
) -> dict[str, Any]:
    """Restore controller LIST_DIR from runtime_backups; optionally redeploy to nodes."""
    result = rollback_from_runtime_backup(
        backup_stamp,
        selected_files=selected_files,
        progress_callback=progress_callback,
    )
    if not result.get("success"):
        maybe_notify_rollback_failed(db, result, triggered_by=triggered_by)
        return result

    result["artifact_stamp"] = compute_artifact_stamp()

    if redeploy_after:
        deploy_result = run_multi_deploy(
            db,
            target_node_ids=target_node_ids,
            all_online=all_online,
            target_node_id=target_node_id,
            files=result.get("restored"),
            sync_after=sync_after,
            apply_after=apply_after,
            triggered_by=triggered_by,
        )
        result["deploy"] = deploy_result.get("deploy")
        result["per_node"] = deploy_result.get("per_node")
        result["nodes_deployed"] = deploy_result.get("nodes_deployed")
        result["nodes_failed"] = deploy_result.get("nodes_failed")
        result["nodes_skipped"] = deploy_result.get("nodes_skipped")
        result["success"] = bool(deploy_result.get("success"))
        if result["success"]:
            result["message"] = (
                f"{result.get('message', '')} · развёрнуто на {deploy_result.get('nodes_deployed', 0)} узел(ов)"
            ).strip(" ·")
        else:
            result["message"] = deploy_result.get("message") or result.get("message")

    maybe_notify_rollback_failed(db, result, triggered_by=triggered_by)
    return result
