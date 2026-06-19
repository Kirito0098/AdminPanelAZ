"""Central HA replicate dispatcher tests (step 0.2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus, User, UserActionLog, UserRole, VpnConfig, VpnType
from app.services.node_sync.groups import serialize_replica_node_ids
from app.services.node_sync.replicate import (
    ReplicateOperation,
    get_shadow_configs,
    iter_replica_adapters,
    replicate_to_replicas,
)


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


def test_replicate_early_exit_when_not_auto(auto_group_db):
    db, group, _primary, _replica, primary_config = auto_group_db
    group.sync_mode = "manual_full"
    db.commit()

    result = replicate_to_replicas(
        db,
        group,
        ReplicateOperation.CLIENT_CREATE,
        {"primary_config": primary_config},
    )

    assert result.skipped is True
    assert result.successes == []
    assert result.errors == []


def test_replicate_empty_replica_list(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online)
    db_session.add(primary)
    db_session.commit()
    user = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
    db_session.add(user)
    db_session.commit()
    group = NodeSyncGroup(
        name="HA-empty",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([]),
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    db_session.add(group)
    db_session.commit()
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="solo",
        vpn_type=VpnType.wireguard,
        owner_id=user.id,
    )
    db_session.add(primary_config)
    db_session.commit()

    result = replicate_to_replicas(
        db_session,
        group,
        ReplicateOperation.CLIENT_CREATE,
        {"primary_config": primary_config},
    )

    assert result.skipped is False
    assert result.successes == []
    assert result.errors == []
    assert group.sync_status == SyncStatus.synced
    assert list(iter_replica_adapters(db_session, group)) == []


def test_replicate_partial_failure_sets_failed_and_audits(auto_group_db, monkeypatch):
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
        result = replicate_to_replicas(
            db,
            group,
            ReplicateOperation.CLIENT_CREATE,
            {"primary_config": primary_config},
        )

    assert len(result.successes) == 1
    assert len(result.errors) == 1
    assert group.sync_status == SyncStatus.failed
    assert group.last_sync_error == "disk full"
    log = (
        db.query(UserActionLog)
        .filter(UserActionLog.action == "ha_replicate_partial_failure")
        .one()
    )
    assert "client=alice" in log.details
    assert "successful_replicas=replica" in log.details
    assert "failed_replicas=replica2" in log.details


def test_get_shadow_configs_returns_linked_replica_rows(auto_group_db):
    db, group, _primary, replica, primary_config = auto_group_db
    shadow = VpnConfig(
        node_id=replica.id,
        client_name="alice",
        vpn_type=VpnType.wireguard,
        owner_id=primary_config.owner_id,
        sync_group_id=group.id,
        ha_primary_config_id=primary_config.id,
    )
    db.add(shadow)
    db.commit()

    shadows = get_shadow_configs(db, group, primary_config)

    assert len(shadows) == 1
    assert shadows[0].node_id == replica.id


def test_stub_operation_not_implemented(auto_group_db):
    db, group, _primary, _replica, primary_config = auto_group_db

    result = replicate_to_replicas(
        db,
        group,
        ReplicateOperation.POLICY_APPLY,
        {"primary_config": primary_config},
    )

    assert result.skipped is False
    assert result.successes == []
    assert len(result.errors) == 1
    assert "not implemented" in result.errors[0]["error"]
