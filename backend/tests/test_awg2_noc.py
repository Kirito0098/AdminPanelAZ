from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.services.awg2_noc import awg2_client_to_peer, fetch_awg2_peers_for_adapter, peers_from_awg2_monitoring
from app.services.wireguard_status import wireguard_peer_is_online


def test_awg2_client_to_peer_online_from_age():
    # Use wall-clock now: wireguard_peer_is_online() compares against utcnow().
    now = datetime.utcnow()
    peer = awg2_client_to_peer(
        {
            "name": "ivan",
            "iface": "antizapret-awg",
            "online": True,
            "handshake_age_s": 30,
            "rx": 10,
            "tx": 20,
            "pubkey": "pk1",
            "endpoint": "203.0.113.9:51820",
        },
        now=now,
    )
    assert peer.client_name == "ivan"
    assert peer.interface == "antizapret-awg"
    assert peer.public_key == "pk1"
    assert peer.endpoint == "203.0.113.9:51820"
    assert peer.transfer_rx == 10 and peer.transfer_tx == 20
    assert peer.latest_handshake == (now - timedelta(seconds=30)).isoformat()
    assert wireguard_peer_is_online(peer)


def test_awg2_client_stale_not_online():
    now = datetime.utcnow()
    peer = awg2_client_to_peer(
        {"name": "x", "iface": "vpn-awg", "handshake_age_s": 400, "rx": 0, "tx": 0, "pubkey": "pk"},
        now=now,
    )
    assert not wireguard_peer_is_online(peer)


def test_fetch_skips_when_not_installed():
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {"installed": False}
    assert fetch_awg2_peers_for_adapter(adapter) == []
    adapter.get_awg2_monitoring.assert_not_called()


def test_fetch_returns_peers_when_installed():
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {"installed": True}
    adapter.get_awg2_monitoring.return_value = {
        "clients": [
            {
                "name": "a",
                "iface": "antizapret-awg",
                "online": True,
                "handshake_age_s": 10,
                "rx": 1,
                "tx": 2,
                "pubkey": "pk",
                "endpoint": "1.2.3.4:1",
            }
        ]
    }
    peers = fetch_awg2_peers_for_adapter(adapter)
    assert len(peers) == 1 and peers[0].client_name == "a"


def test_fetch_swallows_adapter_errors():
    adapter = MagicMock()
    adapter.get_awg2_health.side_effect = RuntimeError("down")
    assert fetch_awg2_peers_for_adapter(adapter) == []
