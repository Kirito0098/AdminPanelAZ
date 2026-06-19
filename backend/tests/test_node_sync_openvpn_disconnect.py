"""HA auto-sync OpenVPN disconnect replication tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus, User, UserActionLog, UserRole
from app.services.node_sync.client_ops_sync import (
    maybe_replicate_openvpn_disconnect,
    replicate_openvpn_disconnect,
)
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
    return db_session, group, primary, replica


def test_replicate_openvpn_disconnect_calls_all_replicas(auto_group_db):
    db, group, _primary, replica = auto_group_db
    adapter = MagicMock()
    adapter.disconnect_openvpn_client.return_value = {"success": True, "profile": "vpn-tcp"}

    with patch("app.services.node_sync.client_ops_sync.iter_replica_adapters") as mock_iter:
        mock_iter.return_value = [(replica, adapter)]
        result = replicate_openvpn_disconnect(db, group, "alice")

    assert result.skipped is False
    assert result.errors == []
    assert len(result.successes) == 1
    assert result.successes[0]["node_id"] == replica.id
    adapter.disconnect_openvpn_client.assert_called_once_with("alice")
    db.refresh(group)
    assert group.sync_status == SyncStatus.synced


def test_replicate_openvpn_disconnect_client_not_connected_is_not_error(auto_group_db):
    db, group, _primary, replica = auto_group_db
    adapter = MagicMock()
    adapter.disconnect_openvpn_client.return_value = {
        "success": False,
        "message": "Клиент alice не найден среди подключённых",
    }

    with patch("app.services.node_sync.client_ops_sync.iter_replica_adapters") as mock_iter:
        mock_iter.return_value = [(replica, adapter)]
        result = replicate_openvpn_disconnect(db, group, "alice")

    assert result.errors == []
    assert len(result.successes) == 1
    assert result.successes[0]["skipped"] is True
    db.refresh(group)
    assert group.sync_status == SyncStatus.synced


def test_replicate_openvpn_disconnect_adapter_failure_sets_sync_failed(auto_group_db):
    db, group, _primary, replica = auto_group_db
    adapter = MagicMock()
    adapter.disconnect_openvpn_client.side_effect = ConnectionError("replica offline")

    with patch("app.services.node_sync.client_ops_sync.iter_replica_adapters") as mock_iter, patch(
        "app.services.node_sync.client_ops_sync.finalize_replicate_outcome",
    ) as mock_finalize:
        mock_iter.return_value = [(replica, adapter)]
        result = replicate_openvpn_disconnect(db, group, "alice")

    assert result.successes == []
    assert len(result.errors) == 1
    assert "replica offline" in result.errors[0]["error"]
    mock_finalize.assert_called_once()
    finalize_kwargs = mock_finalize.call_args.kwargs
    assert finalize_kwargs["audit_on_partial_failure"] is True
    assert finalize_kwargs["payload"] == {"client_name": "alice"}


def test_replicate_openvpn_disconnect_partial_failure_logs_action(auto_group_db, monkeypatch):
    db, group, _primary, replica = auto_group_db
    replica2 = Node(name="replica2", host="10.0.0.3", port=9100, status=NodeStatus.online)
    db.add(replica2)
    db.commit()
    group.replica_node_ids = serialize_replica_node_ids([replica.id, replica2.id])
    db.commit()

    adapter_ok = MagicMock()
    adapter_ok.disconnect_openvpn_client.return_value = {"success": True}
    adapter_fail = MagicMock()
    adapter_fail.disconnect_openvpn_client.side_effect = RuntimeError("socket timeout")

    def iter_adapters(_db, _group):
        yield replica, adapter_ok
        yield replica2, adapter_fail

    monkeypatch.setattr(
        "app.services.node_sync.replicate.get_settings",
        lambda: Settings(audit_log_enabled=True),
    )

    with patch("app.services.node_sync.client_ops_sync.iter_replica_adapters", side_effect=iter_adapters):
        result = replicate_openvpn_disconnect(db, group, "alice")

    assert len(result.successes) == 1
    assert len(result.errors) == 1
    db.refresh(group)
    assert group.sync_status == SyncStatus.failed
    log = (
        db.query(UserActionLog)
        .filter(UserActionLog.action == "ha_replicate_partial_failure")
        .one()
    )
    assert "client=alice, op=openvpn_disconnect" in log.details
    assert "successful_replicas=replica" in log.details
    assert "failed_replicas=replica2" in log.details


def test_replicate_openvpn_disconnect_manual_mode_skipped(auto_group_db):
    db, group, _primary, _replica = auto_group_db
    group.sync_mode = "manual_full"
    db.commit()

    result = replicate_openvpn_disconnect(db, group, "alice")

    assert result.skipped is True
    assert result.successes == []
    assert result.errors == []


def test_maybe_replicate_openvpn_disconnect_returns_none_without_group(db_session):
    primary = Node(name="solo", host="10.0.0.1", port=9100, status=NodeStatus.online)
    db_session.add(primary)
    db_session.commit()

    result = maybe_replicate_openvpn_disconnect(db_session, node_id=primary.id, client_name="alice")

    assert result is None


def test_maybe_replicate_openvpn_disconnect_returns_none_manual_full(auto_group_db):
    db, group, primary, _replica = auto_group_db
    group.sync_mode = "manual_full"
    db.commit()

    result = maybe_replicate_openvpn_disconnect(db, node_id=primary.id, client_name="alice")

    assert result is None
