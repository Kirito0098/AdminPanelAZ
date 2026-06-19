"""Node sync parity verify tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.node_sync.groups import serialize_replica_node_ids
from app.services.node_sync.verify import verify_sync_group


@pytest.fixture()
def sync_group_db(db_session):
    primary = Node(
        name="primary",
        host="10.0.0.1",
        port=9100,
        status=NodeStatus.online,
        node_metadata="{}",
    )
    replica = Node(
        name="replica",
        host="10.0.0.2",
        port=9100,
        status=NodeStatus.online,
        node_metadata="{}",
    )
    db_session.add_all([primary, replica])
    db_session.commit()
    group = NodeSyncGroup(
        name="HA",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_status=SyncStatus.unknown,
    )
    db_session.add(group)
    db_session.commit()
    return db_session, group, primary, replica


def test_verify_ready_when_parity_matches(sync_group_db):
    db, group, _primary, replica = sync_group_db
    adapter = MagicMock()
    adapter.list_openvpn_clients.return_value = ["alice"]
    adapter.list_wireguard_clients.return_value = ["bob"]
    adapter.get_antizapret_fingerprints.return_value = {"easyrsa3/pki/ca.crt": "abc"}

    with patch("app.services.node_sync.verify.get_adapter_for_node", return_value=adapter):
        result = verify_sync_group(db, group)

    assert result["ready"] is True
    assert result["replicas"][0]["node_id"] == replica.id
    assert result["replicas"][0]["mismatches"] == []
    assert group.sync_status == SyncStatus.synced


def test_verify_mismatch_clients(sync_group_db):
    db, group, _primary, replica = sync_group_db
    primary_adapter = MagicMock()
    primary_adapter.list_openvpn_clients.return_value = ["alice", "extra"]
    primary_adapter.list_wireguard_clients.return_value = []
    primary_adapter.get_antizapret_fingerprints.return_value = {}

    replica_adapter = MagicMock()
    replica_adapter.list_openvpn_clients.return_value = ["alice"]
    replica_adapter.list_wireguard_clients.return_value = []
    replica_adapter.get_antizapret_fingerprints.return_value = {}

    def adapter_for_node(_node):
        if _node.id == group.primary_node_id:
            return primary_adapter
        return replica_adapter

    with patch("app.services.node_sync.verify.get_adapter_for_node", side_effect=adapter_for_node):
        result = verify_sync_group(db, group)

    assert result["ready"] is False
    mismatch = result["replicas"][0]["mismatches"][0]
    assert mismatch["kind"] == "openvpn_clients"
    assert mismatch["only_primary"] == ["extra"]
    stored = json.loads(group.last_verify_result or "{}")
    assert stored["ready"] is False


def test_verify_primary_offline_returns_gracefully(sync_group_db):
    db, group, primary, _replica = sync_group_db
    primary.status = NodeStatus.offline
    db.commit()

    with patch("app.services.node_sync.verify.get_adapter_for_node") as get_adapter:
        result = verify_sync_group(db, group)

    get_adapter.assert_not_called()
    assert result["ready"] is False
    assert result["summary"] == "primary offline или не найден"
    assert result["replicas"] == []
    stored = json.loads(group.last_verify_result or "{}")
    assert stored["ready"] is False
    assert stored["summary"] == "primary offline или не найден"
    assert group.last_verify_at is not None


def test_verify_primary_missing_returns_gracefully(sync_group_db):
    db, group, primary, _replica = sync_group_db

    real_get = db.get

    def get(model, ident, *args, **kwargs):
        if model is Node and ident == group.primary_node_id:
            return None
        return real_get(model, ident, *args, **kwargs)

    with patch.object(db, "get", side_effect=get), patch(
        "app.services.node_sync.verify.get_adapter_for_node",
    ) as get_adapter:
        result = verify_sync_group(db, group)

    get_adapter.assert_not_called()
    assert result["ready"] is False
    assert result["summary"] == "primary offline или не найден"
    stored = json.loads(group.last_verify_result or "{}")
    assert stored["ready"] is False
    assert stored["summary"] == "primary offline или не найден"
    assert group.last_verify_at is not None
    assert primary.id == group.primary_node_id
