"""Tests for monitoring overview enrichment."""

from app.schemas import OpenVpnClient, WireGuardPeer
from app.services.monitoring_overview import enrich_openvpn_clients, enrich_wireguard_peers


def test_enrich_openvpn_client_formats_address_without_protocol_prefix():
    client = OpenVpnClient(
        common_name="alice",
        real_address="udp4:92.36.21.106:4744",
        virtual_address="10.8.0.5",
        bytes_received=100,
        bytes_sent=50,
        connected_since="2026-06-15 10:00:00",
    )
    enriched = enrich_openvpn_clients([client], {})[0]
    assert enriched.display_address == "92.36.21.106:4744"
    assert enriched.client_ip == "92.36.21.106"


def test_enrich_wireguard_peer_adds_node_tags():
    peer = WireGuardPeer(
        interface="vpn-wg",
        public_key="abc",
        endpoint="203.0.113.10:51820",
        client_name="bob",
    )
    enriched = enrich_wireguard_peers([peer], {}, node_id=3, node_name="edge-1")[0]
    assert enriched.display_address == "203.0.113.10:51820"
    assert enriched.node_id == 3
    assert enriched.node_name == "edge-1"
