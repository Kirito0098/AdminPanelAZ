"""Bootstrap shadow VpnConfig links between primary and replicas in auto HA mode."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import NodeSyncGroup, VpnConfig
from app.services.node_sync.groups import get_replica_nodes, is_auto_sync_enabled
from app.services.node_sync.replicate import upsert_shadow_config


def _empty_result() -> dict[str, list[dict[str, Any]]]:
    return {
        "linked": [],
        "created": [],
        "already_linked": [],
        "orphan_replica": [],
        "conflicts": [],
    }


def _shadow_entry(
    *,
    primary_config: VpnConfig,
    replica_node_id: int,
    replica_node_name: str | None,
    shadow: VpnConfig,
    action: str,
) -> dict[str, Any]:
    return {
        "action": action,
        "primary_config_id": primary_config.id,
        "replica_node_id": replica_node_id,
        "replica_node_name": replica_node_name,
        "shadow_config_id": shadow.id,
        "client_name": primary_config.client_name,
        "vpn_type": primary_config.vpn_type.value,
    }


def format_shadow_link_warning(result: dict[str, Any]) -> str | None:
    """Build a short warning for last_sync_error when linking is incomplete."""
    parts: list[str] = []
    conflicts = result.get("conflicts") or []
    orphans = result.get("orphan_replica") or []
    if conflicts:
        parts.append(f"конфликты shadow: {len(conflicts)}")
    if orphans:
        names = ", ".join(str(entry.get("client_name") or "?") for entry in orphans[:5])
        suffix = f" ({names})" if names else ""
        parts.append(f"клиенты только на реплике: {len(orphans)}{suffix}")
    if not parts:
        return None
    return "HA shadow linking: " + "; ".join(parts)


def link_shadow_configs_for_group(db: Session, group: NodeSyncGroup) -> dict[str, Any]:
    """Link existing primary/replica VpnConfig rows for auto-sync event handlers."""
    if not is_auto_sync_enabled(group):
        return _empty_result()

    result = _empty_result()
    replica_nodes = get_replica_nodes(db, group)
    if not replica_nodes:
        return result

    primary_configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == group.primary_node_id,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    )

    for primary_config in primary_configs:
        primary_config.sync_group_id = group.id

        for replica_node in replica_nodes:
            existing = (
                db.query(VpnConfig)
                .filter(
                    VpnConfig.node_id == replica_node.id,
                    VpnConfig.client_name == primary_config.client_name,
                    VpnConfig.vpn_type == primary_config.vpn_type,
                )
                .first()
            )

            if existing is not None and existing.ha_primary_config_id == primary_config.id:
                existing.sync_group_id = group.id
                result["already_linked"].append(
                    _shadow_entry(
                        primary_config=primary_config,
                        replica_node_id=replica_node.id,
                        replica_node_name=replica_node.name,
                        shadow=existing,
                        action="already_linked",
                    )
                )
                continue

            if existing is not None and existing.ha_primary_config_id not in (None, primary_config.id):
                result["conflicts"].append(
                    {
                        "primary_config_id": primary_config.id,
                        "replica_node_id": replica_node.id,
                        "replica_node_name": replica_node.name,
                        "replica_config_id": existing.id,
                        "client_name": primary_config.client_name,
                        "vpn_type": primary_config.vpn_type.value,
                        "ha_primary_config_id": existing.ha_primary_config_id,
                    }
                )
                continue

            created_new = existing is None
            shadow = upsert_shadow_config(db, group, replica_node.id, primary_config, existing)
            bucket = "created" if created_new else "linked"
            result[bucket].append(
                _shadow_entry(
                    primary_config=primary_config,
                    replica_node_id=replica_node.id,
                    replica_node_name=replica_node.name,
                    shadow=shadow,
                    action=bucket,
                )
            )

    primary_keys = {
        (config.client_name, config.vpn_type)
        for config in primary_configs
    }

    for replica_node in replica_nodes:
        replica_configs = (
            db.query(VpnConfig)
            .filter(
                VpnConfig.node_id == replica_node.id,
                VpnConfig.ha_primary_config_id.is_(None),
            )
            .all()
        )
        for config in replica_configs:
            key = (config.client_name, config.vpn_type)
            if key not in primary_keys:
                result["orphan_replica"].append(
                    {
                        "replica_node_id": replica_node.id,
                        "replica_node_name": replica_node.name,
                        "config_id": config.id,
                        "client_name": config.client_name,
                        "vpn_type": config.vpn_type.value,
                    }
                )

    db.flush()
    return result
