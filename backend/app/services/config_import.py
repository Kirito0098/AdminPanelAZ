"""Import VPN clients from node disk into VpnConfig."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Node, VpnConfig, VpnType
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.client_sync import purge_ha_shadow_configs
from app.services.openvpn_cert import resolve_openvpn_cert_days_remaining


@dataclass(frozen=True)
class ConfigDiskSyncResult:
    imported: int
    removed: int


def _is_on_disk(
    client_name: str,
    vpn_type: VpnType,
    ovpn_on_disk: set[str],
    wg_on_disk: set[str],
) -> bool:
    if vpn_type == VpnType.openvpn:
        return client_name in ovpn_on_disk
    return client_name in wg_on_disk


def _remove_stale_configs(
    db: Session,
    node_id: int,
    ovpn_on_disk: set[str],
    wg_on_disk: set[str],
) -> int:
    """Remove VpnConfig rows for this node that no longer exist on disk."""
    removed = 0
    configs = db.query(VpnConfig).filter(VpnConfig.node_id == node_id).all()
    for config in configs:
        if _is_on_disk(config.client_name, config.vpn_type, ovpn_on_disk, wg_on_disk):
            continue
        if config.ha_primary_config_id is None:
            purge_ha_shadow_configs(db, config.id)
        db.delete(config)
        removed += 1
    return removed


def import_clients_from_disk(db: Session, node: Node, owner_id: int) -> ConfigDiskSyncResult:
    """Import OpenVPN/WireGuard clients from node disk and drop stale panel rows."""
    adapter = get_adapter_for_node(node)
    node_id = node.id
    imported = 0

    ovpn_on_disk = set(adapter.list_openvpn_clients())
    wg_on_disk = set(adapter.list_wireguard_clients())

    for client_name in ovpn_on_disk:
        exists = (
            db.query(VpnConfig)
            .filter(
                VpnConfig.node_id == node_id,
                VpnConfig.client_name == client_name,
                VpnConfig.vpn_type == VpnType.openvpn,
            )
            .first()
        )
        cert_days = resolve_openvpn_cert_days_remaining(adapter, client_name)
        if not exists:
            db.add(
                VpnConfig(
                    node_id=node_id,
                    client_name=client_name,
                    vpn_type=VpnType.openvpn,
                    owner_id=owner_id,
                    cert_expire_days=cert_days,
                )
            )
            imported += 1
        elif exists.cert_expire_days is None and cert_days is not None:
            exists.cert_expire_days = cert_days

    for client_name in wg_on_disk:
        exists = (
            db.query(VpnConfig)
            .filter(
                VpnConfig.node_id == node_id,
                VpnConfig.client_name == client_name,
                VpnConfig.vpn_type == VpnType.wireguard,
            )
            .first()
        )
        if not exists:
            db.add(
                VpnConfig(
                    node_id=node_id,
                    client_name=client_name,
                    vpn_type=VpnType.wireguard,
                    owner_id=owner_id,
                )
            )
            imported += 1

    removed = _remove_stale_configs(db, node_id, ovpn_on_disk, wg_on_disk)

    db.commit()
    return ConfigDiskSyncResult(imported=imported, removed=removed)


def format_config_disk_sync_message(result: ConfigDiskSyncResult) -> str:
    if not result.imported and not result.removed:
        return "Синхронизация завершена без изменений"
    parts: list[str] = []
    if result.imported:
        parts.append(f"добавлено {result.imported}")
    if result.removed:
        parts.append(f"удалено {result.removed}")
    return f"Синхронизация: {', '.join(parts)}"
