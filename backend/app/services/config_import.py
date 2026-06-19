"""Import VPN clients from node disk into VpnConfig."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Node, VpnConfig, VpnType
from app.services.node_manager import get_adapter_for_node
from app.services.openvpn_cert import resolve_openvpn_cert_days_remaining


def import_clients_from_disk(db: Session, node: Node, owner_id: int) -> int:
    """Import OpenVPN/WireGuard clients from node disk into VpnConfig."""
    adapter = get_adapter_for_node(node)
    node_id = node.id
    imported = 0

    for client_name in adapter.list_openvpn_clients():
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

    for client_name in adapter.list_wireguard_clients():
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

    db.commit()
    return imported
