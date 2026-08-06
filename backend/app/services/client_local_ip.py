"""Resolve issued VPN tunnel (local) IPs for clients."""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import TrafficSessionState, VpnType
from app.services.node_adapter import NodeAdapter

_WG_INTERFACES = ("antizapret", "vpn")
_CLIENT_RE = re.compile(r"^#\s*Client\s*=\s*(.+)$", re.I)
_PEER_RE = re.compile(r"^\[Peer\]$", re.I)
_ALLOWED_IPS_RE = re.compile(r"^AllowedIPs\s*=\s*(.+)$", re.I)


def normalize_tunnel_ip(raw: str | None) -> str | None:
    """Return a clean display IP from AllowedIPs / virtual_address."""
    if not raw:
        return None
    parts: list[str] = []
    for chunk in str(raw).split(","):
        token = chunk.strip()
        if not token or token in {"(none)", "none", "(null)"}:
            continue
        # Strip CIDR / ports: 10.0.0.2/32, 10.0.0.2:1194 → 10.0.0.2
        host = token.split("/", 1)[0].strip()
        if ":" in host and host.count(":") == 1 and "." in host:
            # IPv4:port
            host = host.split(":", 1)[0].strip()
        if host and host not in parts:
            parts.append(host)
    if not parts:
        return None
    return ", ".join(parts)


def parse_wireguard_allowed_ips_by_client(content: str) -> dict[str, list[str]]:
    """Parse `# Client =` + `AllowedIPs` pairs from a WG server conf."""
    result: dict[str, list[str]] = defaultdict(list)
    pending_client = ""
    current_client = ""

    for raw in (content or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m_client = _CLIENT_RE.match(line)
        if m_client:
            pending_client = m_client.group(1).strip()
            continue
        if _PEER_RE.match(line):
            current_client = pending_client
            pending_client = ""
            continue
        if not current_client:
            continue
        m_ips = _ALLOWED_IPS_RE.match(line)
        if not m_ips:
            continue
        ip = normalize_tunnel_ip(m_ips.group(1))
        if not ip:
            continue
        key = current_client.strip().lower()
        if not key:
            continue
        for part in ip.split(", "):
            if part and part not in result[key]:
                result[key].append(part)
    return dict(result)


def _merge_ip(target: dict[str, list[str]], key: str, raw: str | None) -> None:
    ip = normalize_tunnel_ip(raw)
    if not ip:
        return
    bucket = target.setdefault(key, [])
    for part in ip.split(", "):
        if part and part not in bucket:
            bucket.append(part)


def _format_map(raw: dict[str, list[str]]) -> dict[str, str]:
    return {key: ", ".join(ips) for key, ips in raw.items() if ips}


def load_wireguard_local_ip_map(adapter: NodeAdapter) -> dict[str, str]:
    collected: dict[str, list[str]] = {}
    for interface in _WG_INTERFACES:
        try:
            content = adapter.read_wireguard_server_config(interface)
        except Exception:
            continue
        parsed = parse_wireguard_allowed_ips_by_client(content or "")
        for key, ips in parsed.items():
            bucket = collected.setdefault(key, [])
            for ip in ips:
                if ip not in bucket:
                    bucket.append(ip)
    # Fallback: live wg dump (covers peers still in runtime)
    try:
        for peer in adapter.parse_wireguard_status():
            name = (peer.client_name or "").strip().lower()
            if not name:
                continue
            _merge_ip(collected, name, peer.allowed_ips)
    except Exception:
        pass
    return _format_map(collected)


def load_openvpn_local_ip_map(
    adapter: NodeAdapter,
    db: Session | None = None,
    *,
    node_id: int | None = None,
    client_names: set[str] | None = None,
) -> dict[str, str]:
    collected: dict[str, list[str]] = {}

    try:
        clients, _source = adapter.get_openvpn_status_snapshot()
        for client in clients:
            key = (client.common_name or "").strip().lower()
            if not key:
                continue
            if client_names is not None and key not in client_names:
                continue
            _merge_ip(collected, key, client.virtual_address)
    except Exception:
        pass

    if db is not None and node_id is not None:
        missing = None
        if client_names is not None:
            missing = {name for name in client_names if name not in collected}
            if not missing:
                return _format_map(collected)
        try:
            query = (
                db.query(TrafficSessionState.common_name, TrafficSessionState.virtual_address)
                .filter(
                    TrafficSessionState.node_id == node_id,
                    TrafficSessionState.virtual_address.isnot(None),
                    TrafficSessionState.virtual_address != "",
                )
                .order_by(desc(TrafficSessionState.last_seen_at), desc(TrafficSessionState.id))
            )
            if missing is not None:
                query = query.filter(TrafficSessionState.common_name.in_(list(missing)))
            for common_name, virtual_address in query.limit(2000).all():
                key = (common_name or "").strip().lower()
                if not key or key in collected:
                    continue
                if client_names is not None and key not in client_names:
                    continue
                _merge_ip(collected, key, virtual_address)
        except Exception:
            pass

    return _format_map(collected)


def build_client_local_ip_map(
    adapter: NodeAdapter,
    db: Session | None = None,
    *,
    node_id: int | None = None,
    configs: list | None = None,
) -> dict[str, str]:
    """
    Map lowercased client_name → issued local/VPN IP(s).

    WireGuard: AllowedIPs from server conf (issued at create).
    OpenVPN: live virtual_address, else last known from traffic sessions.
    """
    collected: dict[str, list[str]] = {}

    wg_names: set[str] | None = None
    ovpn_names: set[str] | None = None
    if configs is not None:
        wg_names = set()
        ovpn_names = set()
        for config in configs:
            key = (getattr(config, "client_name", "") or "").strip().lower()
            if not key:
                continue
            vpn_type = getattr(config, "vpn_type", None)
            if vpn_type == VpnType.wireguard or vpn_type == "wireguard":
                wg_names.add(key)
            else:
                ovpn_names.add(key)

    if configs is None or wg_names:
        for key, ip in load_wireguard_local_ip_map(adapter).items():
            if wg_names is not None and key not in wg_names:
                continue
            _merge_ip(collected, key, ip)

    if configs is None or ovpn_names:
        for key, ip in load_openvpn_local_ip_map(
            adapter,
            db,
            node_id=node_id,
            client_names=ovpn_names,
        ).items():
            _merge_ip(collected, key, ip)

    return _format_map(collected)
