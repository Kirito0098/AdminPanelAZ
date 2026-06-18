"""Dissolve sync group — restore independent node state."""

from __future__ import annotations

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus, User, UserRole, VpnConfig, VpnType
from app.services.node_sync.dissolve import dissolve_sync_group
from app.services.node_sync.groups import serialize_replica_node_ids


@pytest.fixture()
def ha_group_db(db_session):
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
        sync_group_id=group.id,
    )
    db_session.add(primary_config)
    db_session.commit()
    shadow = VpnConfig(
        node_id=replica.id,
        client_name="alice",
        vpn_type=VpnType.wireguard,
        owner_id=user.id,
        sync_group_id=group.id,
        ha_primary_config_id=primary_config.id,
    )
    db_session.add(shadow)
    db_session.commit()
    return db_session, group, primary, replica, primary_config, shadow


def test_dissolve_auto_promotes_replica_shadows_and_keeps_configs(ha_group_db):
    db, group, primary, replica, primary_config, shadow = ha_group_db

    result = dissolve_sync_group(db, group)

    assert result["primary_configs_detached"] == 1
    assert result["replica_configs_detached"] == 1

    db.refresh(primary_config)
    db.refresh(shadow)
    assert primary_config.sync_group_id is None
    assert shadow.sync_group_id is None
    assert shadow.ha_primary_config_id is None
    assert db.get(VpnConfig, shadow.id) is not None

    primary_configs = (
        db.query(VpnConfig)
        .filter(VpnConfig.node_id == primary.id, VpnConfig.ha_primary_config_id.is_(None))
        .all()
    )
    replica_configs = (
        db.query(VpnConfig)
        .filter(VpnConfig.node_id == replica.id, VpnConfig.ha_primary_config_id.is_(None))
        .all()
    )
    assert len(primary_configs) == 1
    assert len(replica_configs) == 1
    assert primary_configs[0].client_name == "alice"
    assert replica_configs[0].client_name == "alice"


def test_dissolve_manual_promotes_shadows(ha_group_db):
    db, group, _primary, replica, primary_config, shadow = ha_group_db
    group.sync_mode = "manual_full"
    db.commit()

    result = dissolve_sync_group(db, group)

    assert result["replica_configs_detached"] == 1
    db.refresh(shadow)
    assert shadow.sync_group_id is None
    assert shadow.ha_primary_config_id is None
    assert (
        db.query(VpnConfig)
        .filter(VpnConfig.node_id == replica.id, VpnConfig.ha_primary_config_id.is_(None))
        .count()
        == 1
    )
