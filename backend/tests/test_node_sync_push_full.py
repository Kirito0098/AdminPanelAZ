"""Node sync push-full orchestrator tests."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.models import (
    Node,
    NodeStatus,
    NodeSyncGroup,
    OpenVpnAccessPolicy,
    SyncStatus,
    User,
    UserRole,
    VpnConfig,
    VpnType,
)
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
    admin = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
    db_session.add(admin)
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


def _mock_adapters(group, *, replica_clients: tuple[list[str], list[str]] | None = None):
    ovpn, wg = replica_clients or ([], [])
    primary_adapter = MagicMock()
    primary_adapter.create_antizapret_backup.return_value = {
        "archive_path": "/root/antizapret/backup-1.tar.gz",
        "archive_name": "backup-1.tar.gz",
    }
    primary_adapter.download_antizapret_backup.return_value = b"fake-tar"
    replica_adapter = MagicMock()
    replica_adapter.restore_antizapret_backup.return_value = {"archive_name": "backup-1.tar.gz"}
    replica_adapter.list_openvpn_clients.return_value = ovpn
    replica_adapter.list_wireguard_clients.return_value = wg
    replica_adapter.parse_openvpn_status.return_value = []
    replica_adapter.parse_wireguard_status.return_value = []

    def adapter_for_node(node):
        if node.id == group.primary_node_id:
            return primary_adapter
        return replica_adapter

    return primary_adapter, replica_adapter, adapter_for_node


@contextmanager
def _patch_adapter_for_node(adapter_for_node):
    with (
        patch("app.services.node_sync.push_full.get_adapter_for_node", side_effect=adapter_for_node),
        patch("app.services.config_import.get_adapter_for_node", side_effect=adapter_for_node),
        patch("app.services.node_manager.get_adapter_for_node", side_effect=adapter_for_node),
    ):
        yield


def test_push_full_success(sync_group_db):
    db, group, _primary, _replica = sync_group_db
    _primary_adapter, replica_adapter, adapter_for_node = _mock_adapters(group)

    progress_calls: list[tuple[int, str]] = []

    def progress(percent, stage, _message=None):
        progress_calls.append((percent, stage))

    with _patch_adapter_for_node(adapter_for_node):
        with patch("app.services.node_sync.push_full.verify_sync_group", return_value={"ready": True}):
            result = run_push_full(db, group, progress_callback=progress, auto_verify=True)

    assert result["success"] is True
    assert group.sync_status == SyncStatus.synced
    replica_adapter.restore_antizapret_backup.assert_called_once()
    assert progress_calls[-1][0] == 100


def test_push_full_imports_clients_on_replica(sync_group_db):
    db, group, _primary, replica = sync_group_db
    _primary_adapter, replica_adapter, adapter_for_node = _mock_adapters(
        group,
        replica_clients=(["alice"], ["bob"]),
    )

    with _patch_adapter_for_node(adapter_for_node):
        with patch("app.services.node_sync.push_full.verify_sync_group", return_value={"ready": True}):
            with patch(
                "app.services.config_import.resolve_openvpn_cert_days_remaining",
                return_value=None,
            ):
                result = run_push_full(db, group, auto_verify=False)

    assert result["success"] is True
    configs = db.query(VpnConfig).filter(VpnConfig.node_id == replica.id).all()
    assert len(configs) == 2
    names = {(c.client_name, c.vpn_type) for c in configs}
    assert ("alice", VpnType.openvpn) in names
    assert ("bob", VpnType.wireguard) in names


def test_push_full_copies_policies_and_collects_traffic(sync_group_db):
    db, group, primary, replica = sync_group_db
    db.add(
        OpenVpnAccessPolicy(
            node_id=primary.id,
            client_name="alice",
            is_permanent_blocked=True,
            traffic_limit_bytes=2_000_000,
        )
    )
    db.commit()

    _primary_adapter, replica_adapter, adapter_for_node = _mock_adapters(
        group,
        replica_clients=(["alice"], []),
    )

    with _patch_adapter_for_node(adapter_for_node):
        with patch("app.services.node_sync.push_full.verify_sync_group", return_value={"ready": True}):
            with patch(
                "app.services.config_import.resolve_openvpn_cert_days_remaining",
                return_value=None,
            ):
                result = run_push_full(db, group, auto_verify=False)

    assert result["success"] is True
    policy = (
        db.query(OpenVpnAccessPolicy)
        .filter(
            OpenVpnAccessPolicy.node_id == replica.id,
            OpenVpnAccessPolicy.client_name == "alice",
        )
        .first()
    )
    assert policy is not None
    assert policy.is_permanent_blocked is True
    assert policy.traffic_limit_bytes == 2_000_000
    replica_adapter.parse_openvpn_status.assert_called()
    replica_adapter.parse_wireguard_status.assert_called()


def test_push_full_import_is_idempotent(sync_group_db):
    db, group, _primary, replica = sync_group_db
    _primary_adapter, replica_adapter, adapter_for_node = _mock_adapters(
        group,
        replica_clients=(["alice"], []),
    )

    with _patch_adapter_for_node(adapter_for_node):
        with patch("app.services.node_sync.push_full.verify_sync_group", return_value={"ready": True}):
            with patch(
                "app.services.config_import.resolve_openvpn_cert_days_remaining",
                return_value=None,
            ):
                run_push_full(db, group, auto_verify=False)
                run_push_full(db, group, auto_verify=False)

    assert db.query(VpnConfig).filter(VpnConfig.node_id == replica.id).count() == 1


def test_push_full_links_primary_configs_in_manual_full(sync_group_db):
    db, group, primary, replica = sync_group_db
    assert group.sync_mode == "manual_full"
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=db.query(User).filter(User.role == UserRole.admin).first().id,
    )
    db.add(primary_config)
    db.commit()

    _primary_adapter, replica_adapter, adapter_for_node = _mock_adapters(
        group,
        replica_clients=(["alice"], []),
    )

    with _patch_adapter_for_node(adapter_for_node):
        with patch("app.services.node_sync.push_full.verify_sync_group", return_value={"ready": True}):
            with patch(
                "app.services.config_import.resolve_openvpn_cert_days_remaining",
                return_value=None,
            ):
                result = run_push_full(db, group, auto_verify=False)

    assert result["success"] is True
    assert primary_config.sync_group_id == group.id
    replica_config = (
        db.query(VpnConfig)
        .filter(VpnConfig.node_id == replica.id, VpnConfig.client_name == "alice")
        .first()
    )
    assert replica_config is not None
    assert replica_config.sync_group_id is None
    assert replica_config.ha_primary_config_id is None


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

    with _patch_adapter_for_node(adapter_for_node):
        result = run_push_full(db, group, auto_verify=False)

    assert result["success"] is False
    assert group.sync_status == SyncStatus.failed
    assert "restore failed" in (group.last_sync_error or "")
