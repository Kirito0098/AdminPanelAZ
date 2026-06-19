"""Tear down HA sync group links so member nodes behave independently."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import NodeSyncGroup, VpnConfig
from app.services.node_sync.groups import parse_replica_node_ids


def dissolve_sync_group(db: Session, group: NodeSyncGroup) -> dict[str, Any]:
    """Detach HA links in DB; VPN configs and files on each node are kept as-is."""
    replica_ids = set(parse_replica_node_ids(group.replica_node_ids))

    primary_configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.sync_group_id == group.id,
            VpnConfig.ha_primary_config_id.is_(None),
            VpnConfig.node_id == group.primary_node_id,
        )
        .all()
    )
    primary_config_ids = [config.id for config in primary_configs]

    for config in primary_configs:
        config.sync_group_id = None

    shadow_query = db.query(VpnConfig).filter(VpnConfig.ha_primary_config_id.isnot(None))
    if primary_config_ids:
        shadows = shadow_query.filter(
            (VpnConfig.sync_group_id == group.id) | VpnConfig.ha_primary_config_id.in_(primary_config_ids)
        ).all()
    else:
        shadows = shadow_query.filter(VpnConfig.sync_group_id == group.id).all()

    for shadow in shadows:
        shadow.sync_group_id = None
        shadow.ha_primary_config_id = None

    stray_replica_configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.sync_group_id == group.id,
            VpnConfig.ha_primary_config_id.is_(None),
            VpnConfig.node_id != group.primary_node_id,
        )
        .all()
    )
    for config in stray_replica_configs:
        config.sync_group_id = None

    return {
        "primary_configs_detached": len(primary_configs),
        "replica_configs_detached": len(shadows) + len(stray_replica_configs),
        "replica_node_ids": sorted(replica_ids),
    }
