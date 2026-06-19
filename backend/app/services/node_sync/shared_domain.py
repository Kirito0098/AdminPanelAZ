"""Propagate Sync Group shared_domain into setup hosts on every member node.

Writes ``OPENVPN_HOST`` / ``WIREGUARD_HOST`` = ``shared_domain`` to
``/root/antizapret/setup`` on the primary and all replicas, then runs
``doall.sh`` (apply_config_changes) and ``client.sh 7`` (recreate_profiles) on
each node so the new hosts land in regenerated client profiles.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import Node, NodeSyncGroup, SyncStatus
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.groups import parse_replica_node_ids

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str, str | None], None]


def get_member_nodes(db: Session, group: NodeSyncGroup) -> list[Node]:
    """Return primary + replica nodes (in order, deduplicated, existing only)."""
    node_ids = [group.primary_node_id, *parse_replica_node_ids(group.replica_node_ids)]
    nodes: list[Node] = []
    seen: set[int] = set()
    for node_id in node_ids:
        if node_id is None or node_id in seen:
            continue
        seen.add(node_id)
        node = db.get(Node, node_id)
        if node is not None:
            nodes.append(node)
    return nodes


def apply_shared_domain_to_members(
    db: Session,
    group: NodeSyncGroup,
    *,
    run_apply: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Write shared_domain hosts to setup on all members, then doall.sh + client.sh 7.

    Errors on one node are recorded but never abort the rest (partial failure is
    reflected via ``success=False`` and the ``errors`` list).
    """
    domain = (group.shared_domain or "").strip()
    updates = {"openvpn_host": domain, "wireguard_host": domain}
    nodes = get_member_nodes(db, group)

    def progress(percent: int, stage: str, message: str | None = None) -> None:
        if progress_callback:
            progress_callback(percent, stage, message)

    result: dict[str, Any] = {
        "domain": domain,
        "updated": [],
        "applied": [],
        "errors": [],
    }

    if not domain:
        result["success"] = False
        result["errors"].append({"error": "shared_domain пуст"})
        return result
    if not nodes:
        result["success"] = False
        result["errors"].append({"error": "В группе нет доступных узлов"})
        return result

    total = len(nodes)

    progress(5, "Запись OPENVPN_HOST / WIREGUARD_HOST в setup…")
    for index, node in enumerate(nodes):
        percent = 5 + int((index / total) * 35)
        progress(percent, f"{node.name}: запись хостов в setup…")
        try:
            get_adapter_for_node(node).update_antizapret_settings(updates)
            result["updated"].append({"node_id": node.id, "node_name": node.name})
        except Exception as exc:
            logger.warning("Shared domain setup write failed on %s: %s", node.name, exc)
            result["errors"].append(
                {"node_id": node.id, "node_name": node.name, "stage": "setup", "error": str(exc)}
            )

    if run_apply:
        for index, node in enumerate(nodes):
            percent = 45 + int((index / total) * 50)
            progress(percent, f"{node.name}: doall.sh + client.sh 7…")
            adapter = get_adapter_for_node(node)
            try:
                doall_output = adapter.apply_config_changes()
                recreate_output = adapter.recreate_profiles()
                result["applied"].append(
                    {
                        "node_id": node.id,
                        "node_name": node.name,
                        "doall": (doall_output or "")[:500],
                        "recreate": (recreate_output or "")[:500],
                    }
                )
            except Exception as exc:
                logger.warning("Shared domain apply failed on %s: %s", node.name, exc)
                result["errors"].append(
                    {"node_id": node.id, "node_name": node.name, "stage": "apply", "error": str(exc)}
                )

    progress(100, "Готово")
    result["success"] = not result["errors"]
    return result


def make_shared_domain_callable(group_id: int) -> Callable[..., dict[str, Any]]:
    """Background-task callable: apply shared_domain on a group in a fresh session."""
    captured_group_id = int(group_id)

    def _callable(progress_updater: ProgressCallback | None = None) -> dict[str, Any]:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            group = db.get(NodeSyncGroup, captured_group_id)
            if group is None:
                raise RuntimeError("Sync group не найдена")

            result = apply_shared_domain_to_members(
                db, group, run_apply=True, progress_callback=progress_updater
            )

            group.last_sync_at = datetime.utcnow()
            if result.get("success"):
                if group.sync_status == SyncStatus.pending:
                    group.sync_status = SyncStatus.synced
                group.last_sync_error = None
            else:
                group.sync_status = SyncStatus.failed
                group.last_sync_error = "; ".join(
                    str(item.get("error")) for item in result.get("errors", [])
                )[:1000]
            db.commit()

            return {
                "message": (
                    f"Домен {result.get('domain')} применён на узлах (doall.sh + client.sh 7)"
                    if result.get("success")
                    else "Применение shared domain завершилось с ошибками"
                ),
                "output": json.dumps(result, ensure_ascii=False),
                "success": bool(result.get("success")),
            }
        finally:
            db.close()

    return _callable
