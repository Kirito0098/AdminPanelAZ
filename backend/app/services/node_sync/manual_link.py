"""Link primary VpnConfig rows to HA group in manual_full (variant C — badge without shadows)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import NodeSyncGroup, VpnConfig
from app.services.node_sync.groups import is_auto_sync_enabled


def link_primary_configs_to_group(db: Session, group: NodeSyncGroup) -> int:
    """Set sync_group_id on all primary configs (no replica shadows). Returns count updated."""
    if is_auto_sync_enabled(group):
        return 0

    linked = 0
    for config in (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == group.primary_node_id,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    ):
        if config.sync_group_id != group.id:
            config.sync_group_id = group.id
            linked += 1

    if linked:
        db.commit()
    return linked


def link_primary_config_to_group(db: Session, group: NodeSyncGroup, primary_config: VpnConfig) -> bool:
    """Tag a single primary config with sync_group_id for manual_full HA badge."""
    if is_auto_sync_enabled(group):
        return False
    if primary_config.node_id != group.primary_node_id:
        return False
    if primary_config.ha_primary_config_id is not None:
        return False
    if primary_config.sync_group_id == group.id:
        return False

    primary_config.sync_group_id = group.id
    db.commit()
    return True
