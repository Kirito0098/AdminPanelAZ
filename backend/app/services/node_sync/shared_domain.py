"""Propagate Sync Group shared_domain into setup hosts on every member node.

Writes ``OPENVPN_HOST`` / ``WIREGUARD_HOST`` = ``shared_domain`` to
``/root/antizapret/setup`` on the primary and all replicas, then runs
``doall.sh`` (apply_config_changes) and ``client.sh 7`` (recreate_profiles) on
each node so the new hosts land in regenerated client profiles.

On replicas the locally regenerated ``.ovpn`` files are then replaced with a
byte-copy from the primary: ``client.sh 7`` rebuilds profiles from the
*replica-local* PKI, which breaks byte-parity with the primary (and produces
broken profiles if the replica PKI drifted). The primary is processed first,
so its profiles already contain the new shared domain when they are copied.
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
from app.services.node_sync.openvpn_restart import restart_all_openvpn_servers
from app.services.node_sync.vpn_state_sync import copy_openvpn_profiles_from_primary

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str, str | None], None]


def _shared_domain_success_message(result: dict[str, Any]) -> str:
    domain = str(result.get("domain") or "").strip()
    nodes = [str(item.get("node_name") or item.get("node_id") or "") for item in result.get("updated") or []]
    nodes = [name for name in nodes if name]
    restarted = [
        str(item.get("node_name") or item.get("node_id") or "")
        for item in result.get("openvpn_restart") or []
        if item.get("restarted")
    ]
    restarted = [name for name in restarted if name]
    parts = [f"Домен {domain} записан в setup"]
    if nodes:
        parts.append(f"узлы: {', '.join(nodes)}")
    parts.append("выполнены doall.sh и client.sh 7")
    if restarted:
        parts.append(f"OpenVPN перезапущен на: {', '.join(restarted)}")
    return ". ".join(parts) + "."


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
        "openvpn_restart": [],
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
        primary_adapter = None
        for index, node in enumerate(nodes):
            percent = 45 + int((index / total) * 50)
            progress(percent, f"{node.name}: doall.sh + client.sh 7…")
            adapter = get_adapter_for_node(node)
            is_primary = node.id == group.primary_node_id
            try:
                doall_output = adapter.apply_config_changes()
                recreate_output = adapter.recreate_profiles()
                if is_primary:
                    primary_adapter = adapter
                elif primary_adapter is not None:
                    # Replace locally regenerated .ovpn with a byte-copy from
                    # primary to preserve profile parity (same as Push full).
                    progress(percent, f"{node.name}: копия .ovpn с основного узла…")
                    copy_openvpn_profiles_from_primary(primary_adapter, adapter)
                else:
                    result["errors"].append(
                        {
                            "node_id": node.id,
                            "node_name": node.name,
                            "stage": "profile_copy",
                            "error": (
                                "Копия .ovpn с основного узла пропущена: "
                                "apply на основном узле не выполнен"
                            ),
                        }
                    )
                progress(percent, f"{node.name}: перезапуск OpenVPN…")
                restart_result = restart_all_openvpn_servers(adapter)
                result["openvpn_restart"].append(
                    {
                        "node_id": node.id,
                        "node_name": node.name,
                        **restart_result,
                    }
                )
                if restart_result.get("failed"):
                    result["errors"].append(
                        {
                            "node_id": node.id,
                            "node_name": node.name,
                            "stage": "openvpn_restart",
                            "error": "; ".join(
                                f"{item.get('unit')}: {item.get('error')}"
                                for item in restart_result.get("failed", [])
                            ),
                        }
                    )
                result["applied"].append(
                    {
                        "node_id": node.id,
                        "node_name": node.name,
                        "doall": (doall_output or "")[:500],
                        "recreate": (recreate_output or "")[:500],
                        "openvpn_restarted": list(restart_result.get("restarted") or []),
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
                    _shared_domain_success_message(result)
                    if result.get("success")
                    else "Применение shared domain завершилось с ошибками"
                ),
                "output": json.dumps(result, ensure_ascii=False),
                "success": bool(result.get("success")),
            }
        finally:
            db.close()

    return _callable
