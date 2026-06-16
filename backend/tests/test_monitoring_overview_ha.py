"""Tests for HA aggregation in federated monitoring overview."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus, User, UserRole, VpnConfig, VpnType
from app.schemas import MonitoringService, OpenVpnClient, WireGuardPeer
from app.services.monitoring_overview import build_federated_monitoring_overview
from app.services.node_sync.client_sync import replicate_client_create
from app.services.node_sync.groups import serialize_replica_node_ids


@pytest.fixture()
def ha_monitoring_db(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online)
    replica = Node(name="replica", host="10.0.0.2", port=9100, status=NodeStatus.online)
    standalone = Node(name="solo", host="10.0.0.3", port=9100, status=NodeStatus.online)
    db_session.add_all([primary, replica, standalone])
    db_session.commit()

    user = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
    db_session.add(user)
    db_session.commit()

    group = NodeSyncGroup(
        name="HA",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    db_session.add(group)
    db_session.commit()

    ovpn_primary = VpnConfig(
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=user.id,
        sync_group_id=group.id,
    )
    wg_primary = VpnConfig(
        node_id=primary.id,
        client_name="bob",
        vpn_type=VpnType.wireguard,
        owner_id=user.id,
        sync_group_id=group.id,
    )
    db_session.add_all([ovpn_primary, wg_primary])
    db_session.commit()

    adapter = MagicMock()
    with patch("app.services.node_sync.client_sync.get_adapter_for_node", return_value=adapter):
        replicate_client_create(db_session, group, ovpn_primary)
        replicate_client_create(db_session, group, wg_primary)

    return db_session, group, primary, replica, standalone


def _adapter_for_ha_node(node_name: str):
    adapter = MagicMock()
    adapter.get_server_ip.return_value = "203.0.113.1"
    adapter.get_service_status.return_value = [
        MonitoringService(name="openvpn", status="active", active=True),
    ]
    if node_name == "primary":
        adapter.get_openvpn_status_snapshot.return_value = (
            [
                OpenVpnClient(
                    common_name="alice",
                    real_address="1.2.3.4:1194",
                    virtual_address="10.8.0.2",
                    bytes_received=100,
                    bytes_sent=50,
                    connected_since="now",
                )
            ],
            "status_log",
        )
        adapter.parse_wireguard_status.return_value = []
    elif node_name == "replica":
        adapter.get_openvpn_status_snapshot.return_value = (
            [
                OpenVpnClient(
                    common_name="alice",
                    real_address="5.6.7.8:1194",
                    virtual_address="10.8.0.2",
                    bytes_received=200,
                    bytes_sent=80,
                    connected_since="now",
                )
            ],
            "status_log",
        )
        adapter.parse_wireguard_status.return_value = [
            WireGuardPeer(
                interface="wg0",
                public_key="pk-bob",
                endpoint="9.9.9.9:51820",
                client_name="bob",
                latest_handshake="2026-06-16T10:00:00",
            )
        ]
    else:
        adapter.get_openvpn_status_snapshot.return_value = (
            [
                OpenVpnClient(
                    common_name="carol",
                    real_address="8.8.8.8:1194",
                    virtual_address="10.8.0.9",
                    bytes_received=10,
                    bytes_sent=10,
                    connected_since="now",
                )
            ],
            "status_log",
        )
        adapter.parse_wireguard_status.return_value = []
    return adapter


def test_federated_overview_deduplicates_ha_clients(ha_monitoring_db):
    db, group, _primary, _replica, _standalone = ha_monitoring_db

    def adapter_for(node):
        return _adapter_for_ha_node(node.name)

    with patch("app.services.monitoring_overview.get_adapter_for_node", side_effect=adapter_for), patch(
        "app.services.monitoring_overview.lookup_ips_geo",
        return_value={},
    ), patch("app.services.monitoring_overview.get_active_node", return_value=db.query(Node).filter_by(name="primary").one()):
        overview = build_federated_monitoring_overview(db)

    assert overview.scope == "all"
    assert len(overview.openvpn_clients) == 2
    alice = next(item for item in overview.openvpn_clients if item.common_name == "alice")
    carol = next(item for item in overview.openvpn_clients if item.common_name == "carol")
    assert alice.ha is not None
    assert alice.ha.sync_group_id == group.id
    assert alice.ha.shared_domain == "vpn.example.com"
    assert alice.ha.node_count == 2
    assert alice.node_name is None
    assert alice.real_address == "5.6.7.8:1194"
    assert carol.ha is None

    assert len(overview.wireguard_peers) == 1
    bob = overview.wireguard_peers[0]
    assert bob.client_name == "bob"
    assert bob.ha is not None
    assert bob.ha.shared_domain == "vpn.example.com"

    assert overview.total_connected_openvpn == 2
    assert overview.total_connected_wireguard == 1
    assert sum(item.connected_openvpn for item in overview.nodes_summary) == 3
