"""Compact summaries of the last completed CIDR compile/deploy tasks."""

from app.services.cidr.cidr_tasks import find_last_completed_cidr_task


def summarize_last_compile() -> dict | None:
    task = find_last_completed_cidr_task("cidr_generate_from_db")
    if not task:
        return None
    result = task.get("result") or {}
    updated = result.get("updated") or []
    return {
        "finished_at": task.get("finished_at"),
        "status": task.get("status"),
        "files_updated": len(updated),
        "artifact_stamp": result.get("artifact_stamp"),
        "message": task.get("message"),
    }


def summarize_last_deploy() -> dict | None:
    task = find_last_completed_cidr_task("cidr_deploy")
    if not task:
        return None
    result = task.get("result") or {}
    deploy = result.get("deploy") or {}
    per_node = result.get("per_node") or []
    return {
        "finished_at": task.get("finished_at"),
        "status": task.get("status"),
        "pushed_count": len(deploy.get("pushed") or []),
        "failed_count": len(deploy.get("failed") or []),
        "target_node_id": result.get("target_node_id"),
        "artifact_stamp": result.get("artifact_stamp"),
        "nodes_deployed": result.get("nodes_deployed", len([n for n in per_node if n.get("status") == "success"])),
        "nodes_failed": result.get("nodes_failed", len([n for n in per_node if n.get("status") == "failed"])),
        "nodes_skipped": result.get("nodes_skipped", len([n for n in per_node if n.get("status") == "skipped"])),
        "per_node": per_node,
        "message": task.get("message"),
    }
