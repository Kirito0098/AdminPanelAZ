"""Auto-sync VPN clients from primary to replicas in a sync group."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Node, NodeSyncGroup, SyncStatus, VpnConfig, VpnType
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.groups import get_replica_nodes, is_auto_sync_enabled

logger = logging.getLogger(__name__)


def replicate_client_create(
    db: Session,
    group: NodeSyncGroup,
    primary_config: VpnConfig,
) -> dict[str, Any]:
    """Create matching client on all replicas and linked VpnConfig rows."""
    if not is_auto_sync_enabled(group):
        return {"replicated": [], "skipped": True}

    replicated: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for replica_node in get_replica_nodes(db, group):
        adapter = get_adapter_for_node(replica_node)
        try:
            if primary_config.vpn_type == VpnType.openvpn:
                adapter.add_openvpn_client(
                    primary_config.client_name,
                    primary_config.cert_expire_days or 3650,
                )
            else:
                adapter.add_wireguard_client(primary_config.client_name)
        except Exception as exc:
            logger.warning(
                "HA auto-sync create failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            errors.append({"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)})
            continue

        existing = (
            db.query(VpnConfig)
            .filter(
                VpnConfig.node_id == replica_node.id,
                VpnConfig.client_name == primary_config.client_name,
                VpnConfig.vpn_type == primary_config.vpn_type,
            )
            .first()
        )
        if existing:
            existing.sync_group_id = group.id
            existing.ha_primary_config_id = primary_config.id
            shadow = existing
        else:
            shadow = VpnConfig(
                node_id=replica_node.id,
                client_name=primary_config.client_name,
                vpn_type=primary_config.vpn_type,
                owner_id=primary_config.owner_id,
                cert_expire_days=primary_config.cert_expire_days,
                description=primary_config.description,
                sync_group_id=group.id,
                ha_primary_config_id=primary_config.id,
            )
            db.add(shadow)
        db.flush()
        replicated.append({"node_id": replica_node.id, "config_id": shadow.id})

    primary_config.sync_group_id = group.id
    primary_config.ha_primary_config_id = None

    if errors:
        group.sync_status = SyncStatus.failed
        group.last_sync_error = errors[0]["error"]
    else:
        group.sync_status = SyncStatus.synced
        group.last_sync_error = None

    db.commit()
    return {"replicated": replicated, "errors": errors, "skipped": False}


def replicate_client_delete(
    db: Session,
    group: NodeSyncGroup,
    primary_config: VpnConfig,
) -> dict[str, Any]:
    """Delete client from replicas and remove shadow VpnConfig rows."""
    if not is_auto_sync_enabled(group):
        return {"deleted": [], "skipped": True}

    deleted: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    shadows = (
        db.query(VpnConfig)
        .filter(VpnConfig.ha_primary_config_id == primary_config.id)
        .all()
    )
    for shadow in shadows:
        replica_node = db.get(Node, shadow.node_id)
        if not replica_node:
            db.delete(shadow)
            continue
        adapter = get_adapter_for_node(replica_node)
        try:
            if shadow.vpn_type == VpnType.openvpn:
                adapter.delete_openvpn_client(shadow.client_name)
            else:
                adapter.delete_wireguard_client(shadow.client_name)
        except Exception as exc:
            logger.warning(
                "HA auto-sync delete failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            errors.append({"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)})
            continue
        deleted.append({"node_id": replica_node.id, "config_id": shadow.id})
        db.delete(shadow)

    if errors:
        group.sync_status = SyncStatus.failed
        group.last_sync_error = errors[0]["error"]
    else:
        group.last_sync_error = None

    db.commit()
    return {"deleted": deleted, "errors": errors, "skipped": False}


def maybe_replicate_create(db: Session, *, node_id: int, primary_config: VpnConfig) -> dict[str, Any] | None:
    from app.services.node_sync.groups import find_sync_group_for_primary

    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    return replicate_client_create(db, group, primary_config)


def maybe_replicate_delete(db: Session, *, node_id: int, primary_config: VpnConfig) -> dict[str, Any] | None:
    from app.services.node_sync.groups import find_sync_group_for_primary

    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    return replicate_client_delete(db, group, primary_config)
