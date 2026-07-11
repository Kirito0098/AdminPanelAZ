from unittest.mock import MagicMock, patch

from app.models import SyncStatus
from app.services.node_sync import push_full


def _make_node(node_id: int, name: str) -> MagicMock:
    node = MagicMock()
    node.id = node_id
    node.name = name
    return node


def _make_group(*, primary_id: int = 1, replica_ids: list[int] | None = None) -> MagicMock:
    group = MagicMock()
    group.id = 10
    group.primary_node_id = primary_id
    group.replica_node_ids = replica_ids or [2, 3, 4]
    group.sync_mode = "auto"
    group.sync_status = SyncStatus.pending
    group.last_sync_error = None
    group.last_sync_at = None
    return group


def test_push_full_continue_on_error_processes_all_replicas():
    group = _make_group(replica_ids=[2, 3, 4])
    primary = _make_node(1, "primary-1")
    replica_ok_1 = _make_node(2, "replica-ok-1")
    replica_fail = _make_node(3, "replica-fail")
    replica_ok_2 = _make_node(4, "replica-ok-2")
    admin = MagicMock()

    db = MagicMock()

    def fake_get(model, node_id):
        return {
            1: primary,
            2: replica_ok_1,
            3: replica_fail,
            4: replica_ok_2,
        }.get(node_id)

    db.get.side_effect = fake_get
    db.query.return_value.filter.return_value.first.return_value = admin

    primary_adapter = MagicMock()
    primary_adapter.create_antizapret_backup.return_value = {
        "archive_name": "backup.tar.gz",
        "archive_path": "/tmp/backup.tar.gz",
    }
    primary_adapter.download_antizapret_backup.return_value = b"archive-bytes"

    adapter_ok_1 = MagicMock()
    adapter_ok_2 = MagicMock()
    adapter_fail = MagicMock()
    adapter_fail.restore_antizapret_backup.side_effect = RuntimeError("restore failed")

    adapters = {
        1: primary_adapter,
        2: adapter_ok_1,
        3: adapter_fail,
        4: adapter_ok_2,
    }

    with patch.object(push_full, "validate_sync_group_payload", return_value=[]):
        with patch.object(push_full, "parse_replica_node_ids", return_value=[2, 3, 4]):
            with patch.object(push_full, "get_adapter_for_node", side_effect=lambda node: adapters[node.id]):
                with patch.object(push_full, "read_primary_host_settings", return_value={}):
                    with patch.object(
                        push_full,
                        "restart_all_openvpn_servers",
                        return_value={"restarted": [], "failed": [], "skipped": [], "success": True},
                    ):
                        with patch.object(push_full, "import_clients_from_disk"):
                            with patch.object(push_full, "copy_access_policies_from_node"):
                                with patch.object(push_full, "collect_traffic_snapshot_for_node"):
                                    with patch.object(push_full, "is_auto_sync_enabled", return_value=True):
                                        with patch.object(
                                            push_full,
                                            "link_shadow_configs_for_group",
                                            return_value={"linked": [], "conflicts": [], "orphan_replica": []},
                                        ) as link_shadow:
                                            result = push_full.run_push_full(db, group, auto_verify=False)

    assert len(result["restored"]) == 2
    assert {item["node_id"] for item in result["restored"]} == {2, 4}
    assert len(result["failed"]) == 1
    assert result["failed"][0]["node_id"] == 3
    assert "restore failed" in result["failed"][0]["error"]
    assert result["success"] is False
    assert group.sync_status == SyncStatus.failed
    assert group.last_sync_error is not None
    assert "replica-fail" in group.last_sync_error
    link_shadow.assert_not_called()
