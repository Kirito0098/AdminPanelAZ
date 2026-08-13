"""Map AmneziaWG 2.0 monitoring clients into WireGuardPeer for NOC surfaces."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.schemas import WireGuardPeer


def awg2_client_to_peer(client: dict, *, now: datetime | None = None) -> WireGuardPeer:
    """Convert one AWG2 monitoring client dict into a WireGuardPeer."""
    if now is None:
        now = datetime.utcnow()

    age = client.get("handshake_age_s")
    if isinstance(age, int) and age >= 0:
        latest_handshake = (now - timedelta(seconds=age)).isoformat()
    else:
        latest_handshake = None

    name = client.get("name")
    pubkey = client.get("pubkey") or name
    allowed_ips = client.get("allowed_ips")

    return WireGuardPeer(
        interface=client.get("iface") or "awg2",
        public_key=str(pubkey or ""),
        endpoint=client.get("endpoint"),
        allowed_ips=allowed_ips if allowed_ips is not None else None,
        latest_handshake=latest_handshake,
        transfer_rx=int(client.get("rx") or 0),
        transfer_tx=int(client.get("tx") or 0),
        client_name=name,
    )


def peers_from_awg2_monitoring(payload: dict) -> list[WireGuardPeer]:
    """Map monitoring payload clients to WireGuardPeer list."""
    clients = payload.get("clients") or []
    if not isinstance(clients, list):
        return []
    return [awg2_client_to_peer(c) for c in clients if isinstance(c, dict)]


def fetch_awg2_peers_for_adapter(adapter: Any) -> list[WireGuardPeer]:
    """Fetch AWG2 peers from a node adapter; return [] on missing/errors."""
    try:
        health = adapter.get_awg2_health()
        if not health or not health.get("installed"):
            return []
        return peers_from_awg2_monitoring(adapter.get_awg2_monitoring())
    except Exception:
        return []
