"""NodeSyncGroup CRUD and preflight validation."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus, VpnConfig
from app.services.node_manager import node_metadata_dict


def parse_replica_node_ids(raw: str | list[int] | None) -> list[int]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [int(item) for item in raw]
    try:
        parsed = json.loads(raw or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [int(item) for item in parsed]


def serialize_replica_node_ids(replica_ids: list[int]) -> str:
    return json.dumps(sorted(set(int(item) for item in replica_ids)))


def group_member_node_ids(group: NodeSyncGroup) -> set[int]:
    members = {group.primary_node_id}
    members.update(parse_replica_node_ids(group.replica_node_ids))
    return members


def find_group_for_node(db: Session, node_id: int, *, exclude_group_id: int | None = None) -> NodeSyncGroup | None:
    groups = db.query(NodeSyncGroup).all()
    for group in groups:
        if exclude_group_id is not None and group.id == exclude_group_id:
            continue
        if node_id in group_member_node_ids(group):
            return group
    return None


def validate_sync_group_payload(
    db: Session,
    *,
    primary_node_id: int,
    replica_node_ids: list[int],
    exclude_group_id: int | None = None,
) -> list[str]:
    errors: list[str] = []
    if not replica_node_ids:
        errors.append("Укажите хотя бы один replica-узел")
    if primary_node_id in replica_node_ids:
        errors.append("Primary не может быть в списке replica")

    primary = db.get(Node, primary_node_id)
    if not primary:
        errors.append(f"Primary узел {primary_node_id} не найден")
    elif primary.status != NodeStatus.online:
        errors.append(f"Primary узел «{primary.name}» не online")

    replica_nodes: list[Node] = []
    for node_id in replica_node_ids:
        node = db.get(Node, node_id)
        if not node:
            errors.append(f"Replica узел {node_id} не найден")
            continue
        if node.status != NodeStatus.online:
            errors.append(f"Replica «{node.name}» не online")
        existing = find_group_for_node(db, node_id, exclude_group_id=exclude_group_id)
        if existing:
            errors.append(f"Узел «{node.name}» уже в группе «{existing.name}»")
        replica_nodes.append(node)

    if primary:
        existing = find_group_for_node(db, primary.id, exclude_group_id=exclude_group_id)
        if existing:
            errors.append(f"Primary «{primary.name}» уже в группе «{existing.name}»")

    versions: set[str] = set()
    for node in ([primary] if primary else []) + replica_nodes:
        meta = node_metadata_dict(node)
        version = str(meta.get("antizapret_version") or "").strip()
        if version:
            versions.add(version)
    if len(versions) > 1:
        errors.append(f"Разные версии AntiZapret на узлах: {', '.join(sorted(versions))}")

    return errors


def raise_if_preflight_errors(errors: list[str]) -> None:
    if not errors:
        return
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"errors": errors},
    )


def apply_group_fields(
    group: NodeSyncGroup,
    *,
    name: str | None = None,
    shared_domain: str | None = None,
    primary_node_id: int | None = None,
    replica_node_ids: list[int] | None = None,
    sync_mode: str | None = None,
) -> None:
    if name is not None:
        group.name = name.strip()
    if shared_domain is not None:
        group.shared_domain = shared_domain.strip()
    if primary_node_id is not None:
        group.primary_node_id = primary_node_id
    if replica_node_ids is not None:
        group.replica_node_ids = serialize_replica_node_ids(replica_node_ids)
    if sync_mode is not None:
        group.sync_mode = sync_mode


def is_auto_sync_enabled(group: NodeSyncGroup) -> bool:
    return str(group.sync_mode or "").strip().lower() == "auto"


def find_sync_group_for_primary(db: Session, node_id: int) -> NodeSyncGroup | None:
    return db.query(NodeSyncGroup).filter(NodeSyncGroup.primary_node_id == node_id).first()


def get_sync_group_for_primary_or_raise(db: Session, node_id: int) -> NodeSyncGroup:
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"HA sync group for primary node {node_id} not found",
        )
    return group


def find_sync_group_containing_node(
    db: Session,
    node_id: int,
) -> tuple[NodeSyncGroup | None, str]:
    group = find_group_for_node(db, node_id)
    if not group:
        return None, ""
    if group.primary_node_id == node_id:
        return group, "primary"
    return group, "replica"


def build_ha_node_context(db: Session, node_id: int) -> dict[str, Any] | None:
    group, role = find_sync_group_containing_node(db, node_id)
    if not group or not role:
        return None
    primary = db.get(Node, group.primary_node_id)
    return {
        "sync_group_id": group.id,
        "group_name": group.name,
        "shared_domain": group.shared_domain,
        "role": role,
        "primary_node_id": group.primary_node_id,
        "primary_node_name": primary.name if primary else None,
        "sync_mode": group.sync_mode,
        "sync_status": group.sync_status.value if hasattr(group.sync_status, "value") else str(group.sync_status),
    }


def _raise_ha_replica_forbidden(
    db: Session,
    *,
    node_id: int,
    operation_hint: str,
) -> None:
    group, role = find_sync_group_containing_node(db, node_id)
    if not group or role != "replica":
        return
    node = db.get(Node, node_id)
    node_name = node.name if node else str(node_id)
    primary = db.get(Node, group.primary_node_id)
    primary_name = primary.name if primary else str(group.primary_node_id)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            f"Узел «{node_name}» — replica в HA-группе «{group.name}» ({group.shared_domain}). "
            f"{operation_hint} на primary («{primary_name}»)."
        ),
    )


def require_ha_primary_for_client_ops(db: Session, *, node: Node | None = None) -> None:
    """Reject client create/delete/cert mutations on HA replica nodes."""
    if node is None:
        from app.services.node_manager import get_active_node

        node = get_active_node(db)
    _raise_ha_replica_forbidden(
        db,
        node_id=node.id,
        operation_hint="Создавайте и изменяйте клиентов",
    )


def require_ha_primary_node(db: Session, node_id: int) -> None:
    """Reject per-node mutations (e.g. node defaults) on HA replica nodes."""
    _raise_ha_replica_forbidden(
        db,
        node_id=node_id,
        operation_hint="Меняйте политику по умолчанию",
    )


def get_replica_nodes(db: Session, group: NodeSyncGroup) -> list[Node]:
    replica_ids = parse_replica_node_ids(group.replica_node_ids)
    if not replica_ids:
        return []
    nodes = db.query(Node).filter(Node.id.in_(replica_ids)).all()
    by_id = {node.id: node for node in nodes}
    return [by_id[node_id] for node_id in replica_ids if node_id in by_id]


def build_ha_metadata(group: NodeSyncGroup | None) -> dict[str, Any] | None:
    if not group:
        return None
    replica_count = len(parse_replica_node_ids(group.replica_node_ids))
    return {
        "sync_group_id": group.id,
        "shared_domain": group.shared_domain,
        "node_count": replica_count + 1,
        "sync_status": group.sync_status.value if hasattr(group.sync_status, "value") else str(group.sync_status),
        "sync_mode": group.sync_mode,
    }


def _client_counts_by_node(db: Session, node_ids: list[int]) -> dict[int, int]:
    """VpnConfig rows per node — used to warn before a destructive replica overwrite."""
    if not node_ids:
        return {}
    rows = (
        db.query(VpnConfig.node_id, func.count(VpnConfig.id))
        .filter(VpnConfig.node_id.in_(node_ids))
        .group_by(VpnConfig.node_id)
        .all()
    )
    return {int(node_id): int(count) for node_id, count in rows}


def _build_members(
    group: NodeSyncGroup,
    nodes_by_id: dict[int, Node],
    replicas: list[int],
    client_counts: dict[int, int],
) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    ordered = [(group.primary_node_id, "primary"), *((rid, "replica") for rid in replicas)]
    for node_id, role in ordered:
        node = nodes_by_id.get(node_id)
        status_value = (
            node.status.value if node and hasattr(node.status, "value") else (str(node.status) if node else "unknown")
        )
        members.append(
            {
                "node_id": node_id,
                "node_name": node.name if node else None,
                "role": role,
                "host": node.host if node else None,
                "online": bool(node and node.status == NodeStatus.online),
                "status": status_value,
                "client_count": int(client_counts.get(node_id, 0)),
            }
        )
    return members


def group_to_dict(group: NodeSyncGroup, db: Session) -> dict[str, Any]:
    replicas = parse_replica_node_ids(group.replica_node_ids)
    member_ids = [group.primary_node_id, *replicas]
    nodes_by_id = {
        node.id: node
        for node in db.query(Node).filter(Node.id.in_(member_ids)).all()
    }
    primary = nodes_by_id.get(group.primary_node_id)
    client_counts = _client_counts_by_node(db, member_ids)
    verify_result = None
    if group.last_verify_result:
        try:
            verify_result = json.loads(group.last_verify_result)
        except (TypeError, ValueError, json.JSONDecodeError):
            verify_result = None
    ready = None
    if isinstance(verify_result, dict) and "ready" in verify_result:
        ready = bool(verify_result.get("ready"))
    return {
        "members": _build_members(group, nodes_by_id, replicas, client_counts),
        "ready": ready,
        "id": group.id,
        "name": group.name,
        "shared_domain": group.shared_domain,
        "primary_node_id": group.primary_node_id,
        "primary_node_name": primary.name if primary else None,
        "replica_node_ids": replicas,
        "replica_node_names": [nodes_by_id[nid].name for nid in replicas if nid in nodes_by_id],
        "sync_mode": group.sync_mode,
        "sync_status": group.sync_status.value if hasattr(group.sync_status, "value") else str(group.sync_status),
        "last_sync_at": group.last_sync_at,
        "last_verify_at": group.last_verify_at,
        "last_sync_task_id": group.last_sync_task_id,
        "last_sync_error": group.last_sync_error,
        "last_verify_result": verify_result,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }
