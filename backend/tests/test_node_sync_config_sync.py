"""HA auto-sync config file replication tests (step B.1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.file_editor import EDITABLE_FILES
from app.services.node_sync.config_sync import replicate_config_files
from app.services.node_sync.groups import serialize_replica_node_ids


@pytest.fixture()
def auto_group_db(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online)
    replica = Node(name="replica", host="10.0.0.2", port=9100, status=NodeStatus.online)
    outsider = Node(name="outsider", host="10.0.0.9", port=9100, status=NodeStatus.online)
    db_session.add_all([primary, replica, outsider])
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
    return db_session, group, primary, replica, outsider


def test_replicate_config_files_happy_path(auto_group_db):
    db, group, primary, replica, outsider = auto_group_db
    primary_adapter = MagicMock()
    primary_adapter.read_config_file.return_value = "example.com\n"
    replica_adapter = MagicMock()
    outsider_adapter = MagicMock()

    def get_adapter(node):
        if node.id == primary.id:
            return primary_adapter
        if node.id == replica.id:
            return replica_adapter
        return outsider_adapter

    with patch("app.services.edit_files_transfer.get_adapter_for_node", side_effect=get_adapter):
        result = replicate_config_files(
            db,
            group,
            ["include_hosts"],
            run_doall=True,
        )

    assert result["skipped"] is False
    assert result["success"] is True
    assert len(result["replicated"]) == 1
    assert result["replicated"][0]["node_id"] == replica.id
    assert group.sync_status == SyncStatus.synced
    primary_adapter.read_config_file.assert_called_once_with("include-hosts.txt")
    replica_adapter.write_config_file.assert_called_once_with("include-hosts.txt", "example.com\n")
    replica_adapter.apply_config_changes.assert_called_once()
    outsider_adapter.write_config_file.assert_not_called()


def test_replicate_config_files_skips_excluded_warper_include_ips(auto_group_db, monkeypatch):
    db, group, primary, replica, _outsider = auto_group_db
    monkeypatch.setitem(EDITABLE_FILES, "warper_include_ips", "warper-include-ips.txt")

    primary_adapter = MagicMock()
    primary_adapter.read_config_file.return_value = "content\n"
    replica_adapter = MagicMock()
    written: list[str] = []

    def capture_write(fname, _content):
        written.append(fname)

    replica_adapter.write_config_file.side_effect = capture_write

    def get_adapter(node):
        if node.id == primary.id:
            return primary_adapter
        if node.id == replica.id:
            return replica_adapter
        return MagicMock()

    with patch("app.services.edit_files_transfer.get_adapter_for_node", side_effect=get_adapter):
        result = replicate_config_files(
            db,
            group,
            ["include_hosts", "warper_include_ips"],
            run_doall=False,
        )

    assert result["success"] is True
    assert result["excluded_file_keys"] == ["warper_include_ips"]
    assert written == ["include-hosts.txt"]
    read_calls = [call.args[0] for call in primary_adapter.read_config_file.call_args_list]
    assert read_calls == ["include-hosts.txt"]
    assert group.sync_status == SyncStatus.synced


def test_replicate_config_files_partial_node_failure_sets_failed(auto_group_db):
    db, group, primary, replica, _outsider = auto_group_db
    replica2 = Node(name="replica2", host="10.0.0.3", port=9100, status=NodeStatus.online)
    db.add(replica2)
    db.commit()
    group.replica_node_ids = serialize_replica_node_ids([replica.id, replica2.id])
    db.commit()

    primary_adapter = MagicMock()
    primary_adapter.read_config_file.return_value = "example.com\n"
    replica_ok = MagicMock()
    replica_fail = MagicMock()
    replica_fail.write_config_file.side_effect = RuntimeError("disk full")

    def get_adapter(node):
        if node.id == primary.id:
            return primary_adapter
        if node.id == replica.id:
            return replica_ok
        if node.id == replica2.id:
            return replica_fail
        return MagicMock()

    with patch("app.services.edit_files_transfer.get_adapter_for_node", side_effect=get_adapter):
        result = replicate_config_files(db, group, ["include_hosts"])

    assert result["success"] is False
    assert len(result["replicated"]) == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["node_id"] == replica2.id
    assert group.sync_status == SyncStatus.failed
    assert group.last_sync_error == "disk full"
