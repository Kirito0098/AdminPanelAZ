"""manual_full variant C — link primary configs to HA group for badge."""

from __future__ import annotations

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, VpnConfig, VpnType
from app.services.node_sync.groups import serialize_replica_node_ids
from app.services.node_sync.manual_link import link_primary_config_to_group, link_primary_configs_to_group


@pytest.fixture()
def manual_group_db(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online)
    replica = Node(name="replica", host="10.0.0.2", port=9100, status=NodeStatus.online)
    db_session.add_all([primary, replica])
    db_session.commit()
    from app.models import User, UserRole

    user = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
    db_session.add(user)
    db_session.commit()
    group = NodeSyncGroup(
        name="HA manual",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_mode="manual_full",
    )
    db_session.add(group)
    db_session.commit()
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=user.id,
    )
    replica_config = VpnConfig(
        node_id=replica.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=user.id,
    )
    db_session.add_all([primary_config, replica_config])
    db_session.commit()
    return db_session, group, primary, replica, primary_config, replica_config


def test_link_primary_configs_sets_sync_group_id(manual_group_db):
    db, group, _primary, _replica, primary_config, replica_config = manual_group_db
    assert primary_config.sync_group_id is None
    assert replica_config.sync_group_id is None

    linked = link_primary_configs_to_group(db, group)
    assert linked == 1
    assert primary_config.sync_group_id == group.id
    assert replica_config.sync_group_id is None


def test_link_primary_configs_idempotent(manual_group_db):
    db, group, *_rest = manual_group_db
    assert link_primary_configs_to_group(db, group) == 1
    assert link_primary_configs_to_group(db, group) == 0


def test_link_primary_config_single(manual_group_db):
    db, group, _primary, _replica, primary_config, _replica_config = manual_group_db
    assert link_primary_config_to_group(db, group, primary_config) is True
    assert primary_config.sync_group_id == group.id
    assert link_primary_config_to_group(db, group, primary_config) is False


def test_link_skipped_for_auto_mode(manual_group_db):
    db, group, *_rest = manual_group_db
    group.sync_mode = "auto"
    db.commit()
    assert link_primary_configs_to_group(db, group) == 0
