"""Node sync push-full orchestrator tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.node_sync.groups import serialize_replica_node_ids
from app.services.node_sync.push_full import run_push_full


@pytest.fixture()
def sync_group_db(db_session):
    primary = Node(
        name="primary",
        host="10.0.0.1",
        port=9100,
        status=NodeStatus.online,
        node_metadata='{"antizapret_version": "v1"}',
    )
    replica = Node(
        name="replica",
        host="10.0.0.2",
        port=9100,
        status=NodeStatus.online,
        node_metadata='{"antizapret_version": "v1"}',
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


def test_push_full_success(sync_group_db):
    db, group, _primary, replica = sync_group_db
    primary_adapter = MagicMock()
    primary_adapter.create_antizapret_backup.return_value = {
        "archive_path": "/root/antizapret/backup-1.tar.gz",
        "archive_name": "backup-1.tar.gz",
    }
    primary_adapter.download_antizapret_backup.return_value = b"fake-tar"
    replica_adapter = MagicMock()
    replica_adapter.restore_antizapret_backup.return_value = {"archive_name": "backup-1.tar.gz"}

    def adapter_for_node(node):
        if node.id == group.primary_node_id:
            return primary_adapter
        return replica_adapter

    progress_calls: list[tuple[int, str]] = []

    def progress(percent, stage, _message=None):
        progress_calls.append((percent, stage))

    with patch("app.services.node_sync.push_full.get_adapter_for_node", side_effect=adapter_for_node):
        with patch("app.services.node_sync.push_full.verify_sync_group", return_value={"ready": True}):
            result = run_push_full(db, group, progress_callback=progress, auto_verify=True)

    assert result["success"] is True
    assert group.sync_status == SyncStatus.synced
    replica_adapter.restore_antizapret_backup.assert_called_once()
    assert progress_calls[-1][0] == 100


def test_push_full_restore_failure(sync_group_db):
    db, group, _primary, _replica = sync_group_db
    primary_adapter = MagicMock()
    primary_adapter.create_antizapret_backup.return_value = {
        "archive_path": "/tmp/backup.tar.gz",
        "archive_name": "backup.tar.gz",
    }
    primary_adapter.download_antizapret_backup.return_value = b"fake-tar"
    replica_adapter = MagicMock()
    replica_adapter.restore_antizapret_backup.side_effect = RuntimeError("restore failed")

    def adapter_for_node(node):
        if node.id == group.primary_node_id:
            return primary_adapter
        return replica_adapter

    with patch("app.services.node_sync.push_full.get_adapter_for_node", side_effect=adapter_for_node):
        result = run_push_full(db, group, auto_verify=False)

    assert result["success"] is False
    assert group.sync_status == SyncStatus.failed
    assert "restore failed" in (group.last_sync_error or "")
