"""Parity verification between primary and replica nodes in a sync group."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.node_adapter import NodeAdapter
from app.services.node_manager import check_node_health, get_adapter_for_node, update_node_from_health
from app.services.node_sync.groups import parse_replica_node_ids


def _refresh_node_online(db: Session, node: Node | None) -> bool:
    """Live health check before parity verify — avoids stale offline status in DB."""
    if not node:
        return False
    health = check_node_health(node)
    update_node_from_health(node, health, db)
    db.refresh(node)
    return node.status == NodeStatus.online


def _client_set_diff(primary: set[str], replica: set[str]) -> dict[str, list[str]]:
    only_primary = sorted(primary - replica)
    only_replica = sorted(replica - primary)
    if not only_primary and not only_replica:
        return {}
    return {"only_primary": only_primary, "only_replica": only_replica}


def verify_sync_group(
    db: Session,
    group: NodeSyncGroup,
    *,
    progress_callback: Callable[[int, str, str | None], None] | None = None,
) -> dict[str, Any]:
    def progress(percent: int, stage: str, message: str | None = None) -> None:
        if progress_callback:
            progress_callback(percent, stage, message)

    progress(5, "Проверка паритета…", "Primary")
    primary_node = db.get(Node, group.primary_node_id)
    primary_online = _refresh_node_online(db, primary_node)
    if not primary_node or not primary_online:
        result = {
            "ready": False,
            "shared_domain": group.shared_domain,
            "primary_node_id": group.primary_node_id,
            "replicas": [],
            "summary": "Основной узел offline или не найден",
        }
        group.last_verify_at = datetime.utcnow()
        group.last_verify_result = json.dumps(result, ensure_ascii=False)
        db.commit()
        return result

    primary_adapter = get_adapter_for_node(primary_node)
    primary_ovpn = set(primary_adapter.list_openvpn_clients())
    primary_wg = set(primary_adapter.list_wireguard_clients())
    primary_fp = primary_adapter.get_antizapret_fingerprints()

    replica_results: list[dict[str, Any]] = []
    replica_ids = parse_replica_node_ids(group.replica_node_ids)
    ready = True

    for index, replica_id in enumerate(replica_ids):
        percent = 10 + int((index / max(len(replica_ids), 1)) * 80)
        node = db.get(Node, replica_id)
        node_name = node.name if node else str(replica_id)
        progress(percent, f"Verify: {node_name}")

        mismatches: list[dict[str, Any]] = []
        online = _refresh_node_online(db, node)
        if not online:
            ready = False
            mismatches.append({"kind": "node_status", "detail": "узел offline или не найден"})
            replica_results.append(
                {
                    "node_id": replica_id,
                    "node_name": node_name,
                    "online": False,
                    "mismatches": mismatches,
                }
            )
            continue

        adapter = get_adapter_for_node(node)
        ovpn_diff = _client_set_diff(primary_ovpn, set(adapter.list_openvpn_clients()))
        if ovpn_diff:
            ready = False
            mismatches.append({"kind": "openvpn_clients", **ovpn_diff})

        wg_diff = _client_set_diff(primary_wg, set(adapter.list_wireguard_clients()))
        if wg_diff:
            ready = False
            mismatches.append({"kind": "wireguard_clients", **wg_diff})

        replica_fp = adapter.get_antizapret_fingerprints()
        all_keys = sorted(set(primary_fp) | set(replica_fp))
        for key in all_keys:
            primary_hash = primary_fp.get(key)
            replica_hash = replica_fp.get(key)
            if primary_hash != replica_hash:
                ready = False
                mismatches.append(
                    {
                        "kind": "fingerprint",
                        "path": key,
                        "primary": primary_hash,
                        "replica": replica_hash,
                    }
                )

        replica_results.append(
            {
                "node_id": replica_id,
                "node_name": node_name,
                "online": True,
                "mismatches": mismatches,
            }
        )

    summary = "Готово к DNS-переключению" if ready else "Расхождения между основным узлом и репликой"
    result = {
        "ready": ready,
        "shared_domain": group.shared_domain,
        "primary_node_id": group.primary_node_id,
        "replicas": replica_results,
        "summary": summary,
    }

    group.last_verify_at = datetime.utcnow()
    group.last_verify_result = json.dumps(result, ensure_ascii=False)
    if ready and group.sync_status != SyncStatus.pending:
        group.sync_status = SyncStatus.synced
    db.commit()

    progress(100, "Verify завершён")
    return result


def verify_sync_group_by_id(db: Session, group_id: int) -> dict[str, Any]:
    group = db.get(NodeSyncGroup, group_id)
    if not group:
        raise ValueError(f"Sync group {group_id} not found")
    return verify_sync_group(db, group)
