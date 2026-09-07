"""Resolve currently online traffic client names for a node."""

from __future__ import annotations

import time
from threading import Lock

from sqlalchemy.orm import Session

from app.models import Node, TrafficSessionState
from app.services.node_manager import _is_vpn_node, get_adapter_for_node
from app.services.wireguard_status import wireguard_peer_is_online

# Coalesce rapid /traffic/active-clients + overview?live=true probes (UI + Telegram).
_LIVE_ACTIVE_TTL_SECONDS = 8.0
_live_active_lock = Lock()
_live_active_cache: dict[int, tuple[float, frozenset[str]]] = {}


def clear_live_active_names_cache() -> None:
    """Test helper — drop TTL cache for live online-name probes."""
    with _live_active_lock:
        _live_active_cache.clear()


def db_active_traffic_client_names(db: Session, node_id: int) -> set[str]:
    rows = (
        db.query(TrafficSessionState.common_name)
        .filter(TrafficSessionState.node_id == node_id, TrafficSessionState.is_active.is_(True))
        .distinct()
        .all()
    )
    return {name for (name,) in rows if name}


def live_active_names_for_node(
    db: Session,
    node: Node,
    *,
    ttl_seconds: float | None = _LIVE_ACTIVE_TTL_SECONDS,
) -> set[str]:
    """Live OVPN/WG/AWG2 online names, with DB session fallback if probe is empty.

    Short TTL cache avoids duplicate adapter status reads when TrafficPage,
    Telegram, or overview?live=true hit the same node within a few seconds.
    """
    if not _is_vpn_node(node):
        return db_active_traffic_client_names(db, node.id)

    ttl = 0.0 if ttl_seconds is None else max(0.0, float(ttl_seconds))
    now = time.monotonic()
    if ttl > 0:
        with _live_active_lock:
            entry = _live_active_cache.get(int(node.id))
            if entry is not None and now < entry[0]:
                return set(entry[1])

    active_names: set[str] = set()
    try:
        adapter = get_adapter_for_node(node)
        ovpn = adapter.parse_openvpn_status()
        wg = adapter.parse_wireguard_status()
        active_names = {c.common_name for c in ovpn if c.common_name}
        active_names.update(
            p.client_name for p in wg if p.client_name and wireguard_peer_is_online(p)
        )
        try:
            from app.services.awg2_noc import fetch_awg2_peers_for_adapter
            from app.services.feature_toggles import is_awg2_enabled

            if is_awg2_enabled(db):
                awg2 = fetch_awg2_peers_for_adapter(adapter)
                active_names.update(
                    p.client_name for p in awg2 if p.client_name and wireguard_peer_is_online(p)
                )
        except Exception:
            pass
    except Exception:
        active_names = set()

    if not active_names:
        active_names = db_active_traffic_client_names(db, node.id)

    if ttl > 0:
        with _live_active_lock:
            _live_active_cache[int(node.id)] = (now + ttl, frozenset(active_names))

    return active_names
