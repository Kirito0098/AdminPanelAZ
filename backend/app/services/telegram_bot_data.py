"""Shared data helpers for Telegram bot handlers (reuse panel services)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import User, VpnConfig, VpnType
from app.services.node_manager import get_active_adapter, get_active_node


def build_dashboard_summary(db: Session, user: User) -> dict:
    adapter = get_active_adapter(db)
    ovpn = adapter.parse_openvpn_status()
    wg = adapter.parse_wireguard_status()
    node = get_active_node(db)
    query = db.query(VpnConfig).filter(VpnConfig.node_id == node.id)
    if user.role.value != "admin":
        query = query.filter(VpnConfig.owner_id == user.id)
    total_configs = query.count()
    return {
        "total_configs": total_configs,
        "connected_openvpn": len(ovpn),
        "connected_wireguard": sum(1 for p in wg if p.latest_handshake),
        "server_ip": adapter.get_server_ip(),
        "timestamp": datetime.utcnow().isoformat(),
    }


def list_user_configs(db: Session, user: User) -> list[VpnConfig]:
    node = get_active_node(db)
    query = db.query(VpnConfig).filter(VpnConfig.node_id == node.id)
    if user.role.value != "admin":
        query = query.filter(VpnConfig.owner_id == user.id)
    return query.order_by(VpnConfig.client_name).all()


def find_config_by_name(db: Session, user: User, name: str) -> VpnConfig | None:
    normalized = (name or "").strip().lower()
    if not normalized:
        return None
    for config in list_user_configs(db, user):
        if config.client_name.lower() == normalized:
            return config
    return None
