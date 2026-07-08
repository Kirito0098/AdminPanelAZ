"""Shared data helpers for Telegram bot handlers (reuse panel services)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import User, VpnConfig, VpnType
from app.services.feature_guards import get_feature_service
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.traffic_limit import human_bytes
from app.services.wireguard_status import wireguard_peer_is_online


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
        "connected_wireguard": sum(1 for p in wg if wireguard_peer_is_online(p)),
        "server_ip": adapter.get_server_ip(),
        "node_name": node.name,
        "timestamp": datetime.utcnow().isoformat(),
    }


def build_server_status_block(db: Session) -> str | None:
    """CPU/RAM/disk/load and live interface throughput for Telegram /status (admin)."""
    if not get_feature_service().is_enabled("server_monitor"):
        return None

    from app.services import telegram_bot_i18n as i18n

    adapter = get_active_adapter(db)
    node = get_active_node(db)
    try:
        metrics = adapter.get_server_metrics(accurate_cpu=True)
        live = adapter.get_server_live_throughput(interval=0.8, max_interfaces=6)
    except Exception:
        return i18n.STATUS_SERVER_UNAVAILABLE.format(node_name=node.name)

    mem_used = human_bytes(int(metrics.get("memory_used") or 0)) or "—"
    mem_total = human_bytes(int(metrics.get("memory_total") or 0)) or "—"
    lines = [
        i18n.STATUS_SERVER_HEADER,
        i18n.STATUS_SERVER_METRICS.format(
            cpu=metrics.get("cpu_percent", "—"),
            ram=metrics.get("memory_percent", "—"),
            mem_used=mem_used,
            mem_total=mem_total,
            disk=metrics.get("disk_percent", "—"),
            uptime=metrics.get("uptime", "—"),
        ),
    ]

    load = metrics.get("load_average") or {}
    if load:
        lines.append(
            i18n.STATUS_SERVER_LOAD.format(
                load_1m=load.get("load_1m", "—"),
                load_5m=load.get("load_5m", "—"),
                load_15m=load.get("load_15m", "—"),
            )
        )

    iface_rows = live.get("interfaces") or []
    if iface_rows:
        iface_lines = []
        for row in iface_rows:
            state = "🟢" if row.get("is_up", True) else "⚪"
            iface_lines.append(
                i18n.STATUS_SERVER_NETWORK_LINE.format(
                    state=state,
                    name=row.get("name", "—"),
                    tx_mbps=row.get("tx_mbps", 0),
                    rx_mbps=row.get("rx_mbps", 0),
                )
            )
        lines.append(i18n.STATUS_SERVER_NETWORK.format(iface_lines="\n".join(iface_lines)))
    else:
        lines.append(i18n.STATUS_SERVER_NETWORK_EMPTY)

    return "\n".join(lines)


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


def search_user_configs(db: Session, user: User, query: str, *, limit: int = 20) -> list[VpnConfig]:
    configs = list_user_configs(db, user)
    normalized = (query or "").strip().lower()
    if not normalized:
        return configs[:limit]
    matched = [config for config in configs if normalized in config.client_name.lower()]
    return matched[:limit]
