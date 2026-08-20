"""Resolve currently online traffic client names for a node."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Node, TrafficSessionState
from app.services.node_manager import get_adapter_for_node
from app.services.wireguard_status import wireguard_peer_is_online


def db_active_traffic_client_names(db: Session, node_id: int) -> set[str]:
    rows = (
        db.query(TrafficSessionState.common_name)
        .filter(TrafficSessionState.node_id == node_id, TrafficSessionState.is_active.is_(True))
        .distinct()
        .all()
    )
    return {name for (name,) in rows if name}


def live_active_names_for_node(db: Session, node: Node) -> set[str]:
    """Live OVPN/WG/AWG2 online names, with DB session fallback if probe is empty."""
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

    return active_names
