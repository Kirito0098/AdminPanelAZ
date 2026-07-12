"""Unit tests for node health score and HA aggregation helpers."""

from __future__ import annotations

from app.schemas import OpenVpnClient, VpnConfigHaInfo
from app.services.monitoring_overview import _aggregate_ha_openvpn_clients
from app.services.node_health_score import compute_node_health_score


def test_offline_node_is_critical_zero():
    score, level = compute_node_health_score(status="offline")
    assert score == 0
    assert level == "critical"


def test_healthy_online_node_is_ok():
    score, level = compute_node_health_score(
        status="online",
        cpu_percent=20,
        memory_percent=30,
        active_services=3,
        total_services=3,
    )
    assert score == 100
    assert level == "ok"


def test_critical_cpu_and_ram_reduce_score():
    score, level = compute_node_health_score(
        status="online",
        cpu_percent=95,
        memory_percent=92,
        active_services=3,
        total_services=3,
    )
    assert score == 50
    assert level == "warn"


def test_inactive_services_and_error():
    score, level = compute_node_health_score(
        status="online",
        error="timeout",
        cpu_percent=10,
        memory_percent=10,
        active_services=1,
        total_services=3,
    )
    # -40 error, -20 inactive (2 * 10)
    assert score == 40
    assert level == "warn"


def test_ha_aggregate_keeps_active_node():
    ha = VpnConfigHaInfo(
        sync_group_id=1,
        shared_domain="vpn.example",
        node_count=2,
        sync_status="synced",
        sync_mode="full",
    )
    ha_lookup = {
        (1, "alice", "openvpn"): (("ha", 1, "openvpn", "alice"), ha),
        (2, "alice", "openvpn"): (("ha", 1, "openvpn", "alice"), ha),
    }
    clients = [
        OpenVpnClient(
            common_name="alice",
            real_address="1.1.1.1:1",
            virtual_address="10.0.0.1",
            bytes_received=100,
            bytes_sent=50,
            connected_since="2026-01-01",
            connected_since_ts=100,
            node_id=1,
            node_name="node-a",
        ),
        OpenVpnClient(
            common_name="alice",
            real_address="2.2.2.2:1",
            virtual_address="10.0.0.2",
            bytes_received=500,
            bytes_sent=200,
            connected_since="2026-01-01",
            connected_since_ts=200,
            node_id=2,
            node_name="node-b",
        ),
    ]
    aggregated = _aggregate_ha_openvpn_clients(clients, ha_lookup)
    assert len(aggregated) == 1
    chosen = aggregated[0]
    assert chosen.node_name == "node-b"
    assert chosen.active_node_id == 2
    assert chosen.active_node_name == "node-b"
    assert {n.node_id for n in chosen.ha_nodes} == {1, 2}
    assert chosen.ha is not None


def test_parse_client_endpoint_strips_openvpn_server_prefix():
    from app.services.ip_geo import parse_client_endpoint

    parsed = parse_client_endpoint("tcp4-server:93.91.6.11:65135")
    assert parsed["lookup_ip"] == "93.91.6.11"
    assert parsed["display_address"] == "93.91.6.11:65135"
    assert parsed["port"] == "65135"
