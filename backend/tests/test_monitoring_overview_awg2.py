"""AWG2 peers wired into monitoring overview."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas import WireGuardPeer
from app.services import monitoring_overview as mo


def test_overview_skips_awg2_when_toggle_off(monkeypatch):
    monkeypatch.setattr(mo, "is_awg2_enabled", lambda _db: False)
    fetch = MagicMock()
    monkeypatch.setattr(mo, "fetch_awg2_peers_for_adapter", fetch)
    peers = mo._load_awg2_peers_for_node(MagicMock(), MagicMock())
    assert peers == []
    fetch.assert_not_called()


def test_overview_loads_peers_when_enabled(monkeypatch):
    monkeypatch.setattr(mo, "is_awg2_enabled", lambda _db: True)
    peer = WireGuardPeer(interface="antizapret-awg", public_key="pk", client_name="ivan")
    monkeypatch.setattr(mo, "fetch_awg2_peers_for_adapter", lambda _a: [peer])
    peers = mo._load_awg2_peers_for_node(MagicMock(), MagicMock())
    assert peers == [peer]


def test_node_summary_counts_awg2_online(monkeypatch):
    now = datetime.utcnow()
    online = WireGuardPeer(
        interface="a",
        public_key="1",
        client_name="o",
        latest_handshake=(now - timedelta(seconds=10)).isoformat(),
    )
    offline = WireGuardPeer(
        interface="a",
        public_key="2",
        client_name="x",
        latest_handshake=(now - timedelta(seconds=400)).isoformat(),
    )
    payload = {
        "node": SimpleNamespace(id=1, name="n", status="online"),
        "ovpn_clients": [],
        "wireguard_peers": [],
        "amneziawg2_peers": [online, offline],
        "services": [],
        "error": None,
        "cpu_percent": None,
        "memory_percent": None,
        "total_traffic_bytes": None,
        "cidr_routes_count": None,
    }
    summary = mo._build_node_summary(payload)
    assert summary.connected_amneziawg2 == 1
