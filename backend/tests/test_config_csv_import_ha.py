"""HA auto-sync tests for CSV import with optional policy columns."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus, User, UserRole, VpnConfig, VpnType, WgAccessPolicy
from app.services.access_policy import AccessPolicyService
from app.services.config_csv_ops import _import_single_row
from app.services.node_sync.groups import serialize_replica_node_ids


@pytest.fixture()
def ha_csv_env(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online, is_local=True)
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


def test_csv_import_applies_traffic_limit_and_replicates_policy(ha_csv_env):
    db, group, primary, replica, user = ha_csv_env
    adapter = MagicMock()
    replica_adapter = MagicMock()
    replica_adapter.block_wireguard_client_runtime.return_value = {"ok": True}

    row = {
        "client_name": "csv-bob",
        "vpn_type": "wireguard",
        "owner_username": "admin",
        "cert_expire_days": "",
        "description": "",
        "traffic_limit_bytes": "5000000",
        "traffic_limit_days": "7",
        "block_mode": "",
        "_line": "2",
    }

    def adapter_for_node(node):
        if node.id == replica.id:
            return replica_adapter
        return adapter

    with (
        patch("app.services.config_csv_ops.get_active_adapter", return_value=adapter),
        patch("app.services.config_csv_ops.get_node_antizapret_path", return_value=MagicMock()),
        patch("app.services.node_sync.replicate.get_adapter_for_node", side_effect=adapter_for_node),
        patch("app.services.node_sync.policy_sync.get_adapter_for_node", return_value=replica_adapter),
        patch.object(AccessPolicyService, "_consumed_bytes", return_value=0),
    ):
        result = _import_single_row(
            db,
            row=row,
            node_id=primary.id,
            default_owner_id=user.id,
            owner_by_username={"admin": user.id},
            actor_username="admin",
        )

    assert result["ok"] is True
    adapter.add_wireguard_client.assert_called_once_with("csv-bob")

    primary_config = (
        db.query(VpnConfig)
        .filter(VpnConfig.node_id == primary.id, VpnConfig.client_name == "csv-bob")
        .one()
    )
    shadow = (
        db.query(VpnConfig)
        .filter(VpnConfig.ha_primary_config_id == primary_config.id, VpnConfig.node_id == replica.id)
        .one()
    )
    assert shadow.client_name == "csv-bob"

    primary_policy = (
        db.query(WgAccessPolicy)
        .filter(WgAccessPolicy.node_id == primary.id, WgAccessPolicy.client_name == "csv-bob")
        .one()
    )
    assert primary_policy.traffic_limit_bytes == 5_000_000
    assert primary_policy.traffic_limit_period_days == 7

    replica_policy = (
        db.query(WgAccessPolicy)
        .filter(WgAccessPolicy.node_id == replica.id, WgAccessPolicy.client_name == "csv-bob")
        .one()
    )
    assert replica_policy.traffic_limit_bytes == 5_000_000
    assert replica_policy.traffic_limit_period_days == 7


def test_csv_import_without_policy_columns_skips_replicate_policy(ha_csv_env):
    db, _group, primary, replica, user = ha_csv_env
    adapter = MagicMock()

    row = {
        "client_name": "csv-plain",
        "vpn_type": "openvpn",
        "owner_username": "admin",
        "cert_expire_days": "365",
        "description": "",
        "traffic_limit_bytes": "",
        "traffic_limit_days": "",
        "block_mode": "",
        "_line": "2",
    }

    with (
        patch("app.services.config_csv_ops.get_active_adapter", return_value=adapter),
        patch("app.services.node_sync.replicate.get_adapter_for_node", return_value=MagicMock()),
        patch("app.services.config_csv_ops.maybe_replicate_policy_op") as mock_replicate_policy,
    ):
        result = _import_single_row(
            db,
            row=row,
            node_id=primary.id,
            default_owner_id=user.id,
            owner_by_username={"admin": user.id},
            actor_username="admin",
        )

    assert result["ok"] is True
    mock_replicate_policy.assert_not_called()
    assert (
        db.query(VpnConfig)
        .filter(VpnConfig.node_id == replica.id, VpnConfig.client_name == "csv-plain")
        .count()
        == 1
    )
