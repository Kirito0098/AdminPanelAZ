"""Local OVPN+WG status snapshot coalesce cache."""

from __future__ import annotations

from app.schemas import OpenVpnClient, WireGuardPeer
from app.services import local_vpn_status_cache as cache_mod
from app.services.local_vpn_status_cache import (
    LocalVpnClientsSnapshot,
    get_local_vpn_clients_snapshot,
)


def _snap(*, cn: str = "Alice") -> LocalVpnClientsSnapshot:
    return LocalVpnClientsSnapshot(
        openvpn_clients=(
            OpenVpnClient(
                common_name=cn,
                real_address="1.1.1.1:1",
                virtual_address="10.0.0.2",
                bytes_received=1,
                bytes_sent=2,
                connected_since="now",
                connected_since_ts=1,
            ),
        ),
        openvpn_data_source="status_log",
        wireguard_peers=(
            WireGuardPeer(
                interface="antizapret",
                public_key="pk",
                client_name="Bob",
            ),
        ),
    )


def test_ttl_cache_skips_second_fetcher():
    cache_mod.clear_local_vpn_status_cache()
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return _snap(cn=f"c{calls['n']}")

    first = get_local_vpn_clients_snapshot(fetch, ttl_seconds=30)
    second = get_local_vpn_clients_snapshot(fetch, ttl_seconds=30)
    assert calls["n"] == 1
    assert first.openvpn_clients[0].common_name == "c1"
    assert second.openvpn_clients[0].common_name == "c1"


def test_zero_ttl_always_refetches():
    cache_mod.clear_local_vpn_status_cache()
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return _snap(cn=f"c{calls['n']}")

    a = get_local_vpn_clients_snapshot(fetch, ttl_seconds=0)
    b = get_local_vpn_clients_snapshot(fetch, ttl_seconds=0)
    assert calls["n"] == 2
    assert a.openvpn_clients[0].common_name == "c1"
    assert b.openvpn_clients[0].common_name == "c2"


def test_clear_forces_refresh():
    cache_mod.clear_local_vpn_status_cache()
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return _snap()

    get_local_vpn_clients_snapshot(fetch, ttl_seconds=60)
    cache_mod.clear_local_vpn_status_cache()
    get_local_vpn_clients_snapshot(fetch, ttl_seconds=60)
    assert calls["n"] == 2


def test_local_adapter_ovpn_and_wg_share_one_probe(monkeypatch):
    from unittest.mock import MagicMock

    from app.services.node_adapter import LocalNodeAdapter

    cache_mod.clear_local_vpn_status_cache()
    service = MagicMock()
    service.parse_openvpn_status.return_value = (
        [
            OpenVpnClient(
                common_name="A",
                real_address="1.1.1.1:1",
                virtual_address="10.0.0.2",
                bytes_received=0,
                bytes_sent=0,
                connected_since="",
            )
        ],
        "status_log",
    )
    service.parse_wireguard_status.return_value = [
        WireGuardPeer(interface="antizapret", public_key="pk", client_name="B")
    ]
    adapter = LocalNodeAdapter(service=service, warper=MagicMock(), awg2=MagicMock())

    clients, source = adapter.get_openvpn_status_snapshot()
    peers = adapter.parse_wireguard_status()
    again = adapter.parse_openvpn_status()

    assert source == "status_log"
    assert clients[0].common_name == "A"
    assert peers[0].client_name == "B"
    assert again[0].common_name == "A"
    assert service.parse_openvpn_status.call_count == 1
    assert service.parse_wireguard_status.call_count == 1
