"""HA auto-sync policy replication tests (step A.1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.models import (
    Node,
    NodeStatus,
    NodeSyncGroup,
    OpenVpnAccessPolicy,
    SyncStatus,
    User,
    UserActionLog,
    UserRole,
    VpnConfig,
    VpnType,
    WgAccessPolicy,
)
from app.services.access_policy import AccessPolicyService
from app.services.node_sync.groups import serialize_replica_node_ids
from app.services.node_sync.policy_sync import maybe_replicate_policy_op, replicate_policy_op


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
    return db_session, group, primary, replica, user


def _add_shadow(db, group, primary_config, replica_node, user):
    shadow = VpnConfig(
        node_id=replica_node.id,
        client_name=primary_config.client_name,
        vpn_type=primary_config.vpn_type,
        owner_id=user.id,
        sync_group_id=group.id,
        ha_primary_config_id=primary_config.id,
    )
    db.add(shadow)
    db.commit()
    return shadow


def _ovpn_adapter():
    banned: set[str] = set()
    adapter = MagicMock()

    def _read(name: str) -> str:
        if name == "banned_clients":
            return "\n".join(sorted(banned)) + ("\n" if banned else "")
        return ""

    def _write(name: str, content: str) -> None:
        if name == "banned_clients":
            banned.clear()
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    banned.add(line)

    adapter.read_config_file.side_effect = _read
    adapter.write_config_file.side_effect = _write
    adapter.ensure_openvpn_ban_check.return_value = None
    return adapter, banned


def _wg_adapter():
    adapter = MagicMock()
    adapter.block_wireguard_client_runtime.return_value = {"ok": True}
    adapter.unblock_wireguard_client_runtime.return_value = {"ok": True}
    return adapter


def _primary_ovpn_policy(db, primary, client_name: str, **fields):
    row = OpenVpnAccessPolicy(node_id=primary.id, client_name=client_name, **fields)
    db.add(row)
    db.commit()
    return row


def _primary_wg_policy(db, primary, client_name: str, **fields):
    row = WgAccessPolicy(
        node_id=primary.id,
        client_name=client_name.strip().lower(),
        **fields,
    )
    db.add(row)
    db.commit()
    return row


def test_replicate_ovpn_permanent_block(auto_group_db):
    db, group, primary, replica, user = auto_group_db
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=user.id,
        sync_group_id=group.id,
    )
    db.add(primary_config)
    db.commit()
    _add_shadow(db, group, primary_config, replica, user)

    primary_svc = AccessPolicyService(db, antizapret_path=MagicMock(), node_id=primary.id)
    primary_adapter, _ = _ovpn_adapter()
    with patch.object(primary_svc, "read_banned_clients", return_value=set()), patch.object(
        primary_svc, "write_banned_clients", return_value=None
    ):
        primary_svc.openvpn_permanent_block("alice", actor="admin")

    replica_adapter, banned = _ovpn_adapter()

    with patch("app.services.node_sync.policy_sync.get_adapter_for_node", return_value=replica_adapter):
        result = replicate_policy_op(
            db,
            group,
            primary_config,
            "block_permanent",
            actor="admin",
        )

    assert result["skipped"] is False
    assert result["errors"] == []
    assert len(result["applied"]) == 1
    replica_row = (
        db.query(OpenVpnAccessPolicy)
        .filter_by(node_id=replica.id, client_name="alice")
        .first()
    )
    assert replica_row is not None
    assert replica_row.is_permanent_blocked is True
    assert "alice" in banned
    assert group.sync_status == SyncStatus.synced


def test_replicate_ovpn_unblock(auto_group_db):
    db, group, primary, replica, user = auto_group_db
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=user.id,
        sync_group_id=group.id,
    )
    db.add(primary_config)
    db.commit()
    _add_shadow(db, group, primary_config, replica, user)
    _primary_ovpn_policy(
        db,
        primary,
        "alice",
        is_permanent_blocked=True,
        block_reason="manual_permanent",
    )
    db.add(
        OpenVpnAccessPolicy(
            node_id=replica.id,
            client_name="alice",
            is_permanent_blocked=True,
            block_reason="manual_permanent",
        )
    )
    db.commit()

    replica_adapter, banned = _ovpn_adapter()
    banned.add("alice")

    with patch("app.services.node_sync.policy_sync.get_adapter_for_node", return_value=replica_adapter):
        result = replicate_policy_op(db, group, primary_config, "unblock", actor="admin")

    assert result["errors"] == []
    replica_row = db.query(OpenVpnAccessPolicy).filter_by(node_id=replica.id, client_name="alice").first()
    assert replica_row.is_permanent_blocked is False
    assert replica_row.block_reason is None
    assert "alice" not in banned


def test_replicate_set_traffic_limit_copies_policy_row(auto_group_db):
    db, group, primary, replica, user = auto_group_db
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="bob",
        vpn_type=VpnType.wireguard,
        owner_id=user.id,
        sync_group_id=group.id,
    )
    db.add(primary_config)
    db.commit()
    _add_shadow(db, group, primary_config, replica, user)
    _primary_wg_policy(
        db,
        primary,
        "bob",
        traffic_limit_bytes=5_000_000,
        traffic_limit_period_days=7,
    )

    replica_adapter = _wg_adapter()

    with patch("app.services.node_sync.policy_sync.get_adapter_for_node", return_value=replica_adapter), patch.object(
        AccessPolicyService,
        "_consumed_bytes",
        return_value=0,
    ):
        result = replicate_policy_op(
            db,
            group,
            primary_config,
            "set_traffic_limit",
            limit_bytes=5_000_000,
            period_days=7,
            actor="admin",
        )

    assert result["errors"] == []
    replica_row = db.query(WgAccessPolicy).filter_by(node_id=replica.id, client_name="bob").first()
    assert replica_row is not None
    assert replica_row.traffic_limit_bytes == 5_000_000
    assert replica_row.traffic_limit_period_days == 7
    replica_adapter.block_wireguard_client_runtime.assert_not_called()


def test_replicate_clear_traffic_limit(auto_group_db):
    db, group, primary, replica, user = auto_group_db
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="bob",
        vpn_type=VpnType.wireguard,
        owner_id=user.id,
        sync_group_id=group.id,
    )
    db.add(primary_config)
    db.commit()
    _add_shadow(db, group, primary_config, replica, user)
    _primary_wg_policy(db, primary, "bob", traffic_limit_bytes=1_000_000)
    db.add(WgAccessPolicy(node_id=replica.id, client_name="bob", traffic_limit_bytes=1_000_000))
    db.commit()

    replica_adapter = _wg_adapter()

    with patch("app.services.node_sync.policy_sync.get_adapter_for_node", return_value=replica_adapter), patch.object(
        AccessPolicyService,
        "_consumed_bytes",
        return_value=0,
    ):
        result = replicate_policy_op(db, group, primary_config, "clear_traffic_limit", actor="admin")

    assert result["errors"] == []
    replica_row = db.query(WgAccessPolicy).filter_by(node_id=replica.id, client_name="bob").first()
    assert replica_row.traffic_limit_bytes is None


def test_replicate_wg_expiry(auto_group_db):
    db, group, primary, replica, user = auto_group_db
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="bob",
        vpn_type=VpnType.wireguard,
        owner_id=user.id,
        sync_group_id=group.id,
    )
    db.add(primary_config)
    db.commit()
    _add_shadow(db, group, primary_config, replica, user)

    expires = datetime.now(timezone.utc) + timedelta(days=30)
    _primary_wg_policy(db, primary, "bob", expires_at=expires)

    replica_adapter = _wg_adapter()

    with patch("app.services.node_sync.policy_sync.get_adapter_for_node", return_value=replica_adapter), patch.object(
        AccessPolicyService,
        "_consumed_bytes",
        return_value=0,
    ):
        result = replicate_policy_op(
            db,
            group,
            primary_config,
            "set_wg_expiry",
            days=30,
            extend=True,
            actor="admin",
        )

    assert result["errors"] == []
    replica_row = db.query(WgAccessPolicy).filter_by(node_id=replica.id, client_name="bob").first()
    assert replica_row is not None
    assert replica_row.expires_at is not None
    replica_adapter.unblock_wireguard_client_runtime.assert_called()


def test_replicate_partial_failure_sets_failed_and_audits(auto_group_db, monkeypatch):
    db, group, primary, replica, user = auto_group_db
    replica2 = Node(name="replica2", host="10.0.0.3", port=9100, status=NodeStatus.online)
    db.add(replica2)
    db.commit()
    group.replica_node_ids = serialize_replica_node_ids([replica.id, replica2.id])
    db.commit()

    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=user.id,
        sync_group_id=group.id,
    )
    db.add(primary_config)
    db.commit()
    _add_shadow(db, group, primary_config, replica, user)

    adapter_ok, _ = _ovpn_adapter()
    adapter_fail = MagicMock()
    adapter_fail.read_config_file.side_effect = RuntimeError("adapter down")

    def get_adapter(node):
        if node.id == replica.id:
            return adapter_ok
        return adapter_fail

    monkeypatch.setattr(
        "app.services.node_sync.policy_sync.get_settings",
        lambda: Settings(audit_log_enabled=True),
    )

    with patch("app.services.node_sync.policy_sync.get_adapter_for_node", side_effect=get_adapter):
        result = replicate_policy_op(db, group, primary_config, "block_permanent", actor="admin")

    assert len(result["applied"]) == 1
    assert len(result["errors"]) == 1
    assert group.sync_status == SyncStatus.failed
    log = (
        db.query(UserActionLog)
        .filter(UserActionLog.action == "ha_replicate_partial_failure")
        .one()
    )
    assert "client=alice" in log.details
    assert "op=block_permanent" in log.details


def test_missing_shadow_fails_without_creating_vpn_config(auto_group_db):
    db, group, primary, replica, user = auto_group_db
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=user.id,
        sync_group_id=group.id,
    )
    db.add(primary_config)
    db.commit()
    before = db.query(VpnConfig).filter(VpnConfig.node_id == replica.id).count()

    replica_adapter, _ = _ovpn_adapter()
    with patch("app.services.node_sync.policy_sync.get_adapter_for_node", return_value=replica_adapter):
        result = replicate_policy_op(db, group, primary_config, "block_permanent", actor="admin")

    assert result["applied"] == []
    assert len(result["errors"]) == 1
    assert "shadow VpnConfig not found" in result["errors"][0]["error"]
    assert db.query(VpnConfig).filter(VpnConfig.node_id == replica.id).count() == before
    assert group.sync_status == SyncStatus.failed


def test_manual_mode_skips_policy_replicate(auto_group_db):
    db, group, primary, replica, user = auto_group_db
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=user.id,
    )
    db.add(primary_config)
    db.commit()
    group.sync_mode = "manual_full"
    db.commit()

    result = replicate_policy_op(db, group, primary_config, "block_permanent", actor="admin")

    assert result["skipped"] is True
    assert (
        db.query(OpenVpnAccessPolicy)
        .filter_by(node_id=replica.id, client_name="alice")
        .first()
        is None
    )


def test_maybe_replicate_policy_op_returns_none_without_group(db_session):
    primary = Node(name="solo", host="10.0.0.1", port=9100, status=NodeStatus.online)
    db_session.add(primary)
    db_session.commit()

    result = maybe_replicate_policy_op(
        db_session,
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        op="block_permanent",
        actor="admin",
    )

    assert result is None


def test_maybe_replicate_policy_op_end_to_end(auto_group_db):
    db, group, primary, replica, user = auto_group_db
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=user.id,
        sync_group_id=group.id,
    )
    db.add(primary_config)
    db.commit()
    _add_shadow(db, group, primary_config, replica, user)

    replica_adapter, banned = _ovpn_adapter()
    with patch("app.services.node_sync.policy_sync.get_adapter_for_node", return_value=replica_adapter):
        result = maybe_replicate_policy_op(
            db,
            node_id=primary.id,
            client_name="alice",
            vpn_type=VpnType.openvpn,
            op="block_permanent",
            actor="admin",
        )

    assert result is not None
    assert result["errors"] == []
    replica_row = (
        db.query(OpenVpnAccessPolicy)
        .filter_by(node_id=replica.id, client_name="alice")
        .first()
    )
    assert replica_row is not None
    assert replica_row.is_permanent_blocked is True
    assert "alice" in banned
