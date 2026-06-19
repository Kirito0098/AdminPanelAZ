"""Node sync auto-replicate client create/delete tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus, User, UserActionLog, UserRole, VpnConfig, VpnType
from app.services.node_sync.client_sync import maybe_replicate_create, replicate_client_create, replicate_client_delete
from app.services.node_sync.groups import serialize_replica_node_ids


@pytest.fixture()
def auto_group_db(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online)
    replica = Node(name="replica", host="10.0.0.2", port=9100, status=NodeStatus.online)
    db_session.add_all([primary, replica])
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
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.wireguard,
        owner_id=user.id,
    )
    db_session.add(primary_config)
    db_session.commit()
    return db_session, group, primary, replica, primary_config


def test_replicate_client_create_on_replicas(auto_group_db):
    db, group, _primary, replica, primary_config = auto_group_db
    adapter = MagicMock()

    with patch("app.services.node_sync.replicate.get_adapter_for_node", return_value=adapter):
        result = replicate_client_create(db, group, primary_config)

    assert result["skipped"] is False
    assert len(result["replicated"]) == 1
    adapter.add_wireguard_client.assert_called_once_with("alice")
    shadow = (
        db.query(VpnConfig)
        .filter(VpnConfig.node_id == replica.id, VpnConfig.client_name == "alice")
        .first()
    )
    assert shadow is not None
    assert shadow.ha_primary_config_id == primary_config.id
    assert primary_config.sync_group_id == group.id


def test_replicate_client_delete_removes_shadows(auto_group_db):
    db, group, _primary, replica, primary_config = auto_group_db
    adapter = MagicMock()

    with patch("app.services.node_sync.replicate.get_adapter_for_node", return_value=adapter):
        replicate_client_create(db, group, primary_config)
        result = replicate_client_delete(db, group, primary_config)

    assert result["skipped"] is False
    adapter.delete_wireguard_client.assert_called_once_with("alice")
    assert (
        db.query(VpnConfig)
        .filter(VpnConfig.ha_primary_config_id == primary_config.id)
        .count()
        == 0
    )


def test_replicate_partial_failure_logs_action(auto_group_db, monkeypatch):
    db, group, _primary, replica, primary_config = auto_group_db
    replica2 = Node(name="replica2", host="10.0.0.3", port=9100, status=NodeStatus.online)
    db.add(replica2)
    db.commit()
    group.replica_node_ids = serialize_replica_node_ids([replica.id, replica2.id])
    db.commit()

    adapter_ok = MagicMock()
    adapter_fail = MagicMock()
    adapter_fail.add_wireguard_client.side_effect = RuntimeError("disk full")

    def get_adapter(node):
        if node.id == replica.id:
            return adapter_ok
        return adapter_fail

    monkeypatch.setattr(
        "app.services.node_sync.replicate.get_settings",
        lambda: Settings(audit_log_enabled=True),
    )

    with patch("app.services.node_sync.replicate.get_adapter_for_node", side_effect=get_adapter):
        result = replicate_client_create(db, group, primary_config)

    assert len(result["replicated"]) == 1
    assert len(result["errors"]) == 1
    log = (
        db.query(UserActionLog)
        .filter(UserActionLog.action == "ha_replicate_partial_failure")
        .one()
    )
    assert "client=alice" in log.details
    assert "successful_replicas=replica" in log.details
    assert "failed_replicas=replica2" in log.details


def test_manual_mode_skips_auto_replicate(auto_group_db):
    db, group, _primary, _replica, primary_config = auto_group_db
    group.sync_mode = "manual_full"
    db.commit()
    result = replicate_client_create(db, group, primary_config)
    assert result["skipped"] is True


def test_manual_mode_maybe_create_links_primary_config(auto_group_db):
    db, group, primary, _replica, primary_config = auto_group_db
    group.sync_mode = "manual_full"
    db.commit()

    result = maybe_replicate_create(db, node_id=primary.id, primary_config=primary_config)

    assert result is not None
    assert result["linked"] is True
    assert result["skipped"] is False
    assert primary_config.sync_group_id == group.id
    assert (
        db.query(VpnConfig)
        .filter(VpnConfig.ha_primary_config_id == primary_config.id)
        .count()
        == 0
    )
