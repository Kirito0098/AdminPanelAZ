"""Sync group PUT/DELETE: refused while a sync runs; membership changes relink HA configs."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus, User, UserRole, VpnConfig, VpnType
from app.routers import node_sync
from app.schemas import NodeSyncGroupUpdate

ADMIN = SimpleNamespace(id=1, username="admin")


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1, username="admin", password_hash="x", role=UserRole.admin, is_active=True))
    for node_id in (1, 2, 3):
        session.add(Node(id=node_id, name=f"node-{node_id}", host=f"10.0.0.{node_id}", status=NodeStatus.online))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _group(db, *, status=SyncStatus.synced, sync_mode="auto", primary=1, replicas=(2,)) -> NodeSyncGroup:
    group = NodeSyncGroup(
        name="ha",
        shared_domain="vpn.example.com",
        primary_node_id=primary,
        replica_node_ids=json.dumps(list(replicas)),
        sync_mode=sync_mode,
        sync_status=status,
    )
    db.add(group)
    db.commit()
    return group


def test_update_rejected_while_group_pending(db):
    group = _group(db, status=SyncStatus.pending)

    with pytest.raises(HTTPException) as exc:
        node_sync.update_sync_group(group.id, NodeSyncGroupUpdate(name="renamed"), ADMIN, db)

    assert exc.value.status_code == 409
    assert exc.value.detail == "Идёт синхронизация, повторите после её окончания"
    db.refresh(group)
    assert group.name == "ha"


def test_delete_rejected_while_group_pending(db):
    group = _group(db, status=SyncStatus.pending)

    with pytest.raises(HTTPException) as exc:
        node_sync.delete_sync_group(group.id, ADMIN, db)

    assert exc.value.status_code == 409
    assert db.get(NodeSyncGroup, group.id) is not None


def test_update_allowed_when_group_not_pending(db):
    group = _group(db, status=SyncStatus.failed)

    response = node_sync.update_sync_group(group.id, NodeSyncGroupUpdate(name="renamed"), ADMIN, db)

    assert response.name == "renamed"


def _config(db, node_id: int, name: str, *, group_id: int | None = None, primary_id: int | None = None) -> VpnConfig:
    config = VpnConfig(
        node_id=node_id,
        client_name=name,
        vpn_type=VpnType.wireguard,
        owner_id=1,
        sync_group_id=group_id,
        ha_primary_config_id=primary_id,
    )
    db.add(config)
    db.commit()
    return config


def test_swapping_primary_relinks_shadows_to_new_primary(db):
    group = _group(db, sync_mode="auto", primary=1, replicas=(2,))
    old_primary = _config(db, 1, "alice", group_id=group.id)
    old_shadow = _config(db, 2, "alice", group_id=group.id, primary_id=old_primary.id)

    node_sync.update_sync_group(
        group.id, NodeSyncGroupUpdate(primary_node_id=2, replica_node_ids=[1]), ADMIN, db
    )

    db.refresh(old_primary)
    db.refresh(old_shadow)
    assert old_shadow.ha_primary_config_id is None
    assert old_shadow.sync_group_id == group.id
    assert old_primary.ha_primary_config_id == old_shadow.id
    assert old_primary.sync_group_id == group.id


def test_replacing_replica_moves_shadow_links(db):
    group = _group(db, sync_mode="auto", primary=1, replicas=(2,))
    primary = _config(db, 1, "alice", group_id=group.id)
    shadow = _config(db, 2, "alice", group_id=group.id, primary_id=primary.id)
    _config(db, 3, "alice")

    node_sync.update_sync_group(group.id, NodeSyncGroupUpdate(replica_node_ids=[3]), ADMIN, db)

    db.refresh(shadow)
    assert shadow.sync_group_id is None
    assert shadow.ha_primary_config_id is None
    new_shadow = db.query(VpnConfig).filter_by(node_id=3, client_name="alice").one()
    assert new_shadow.ha_primary_config_id == primary.id
    assert new_shadow.sync_group_id == group.id


def test_manual_full_primary_change_tags_new_primary_configs(db):
    group = _group(db, sync_mode="manual_full", primary=1, replicas=(2,))
    old = _config(db, 1, "alice", group_id=group.id)
    new = _config(db, 2, "bob")

    node_sync.update_sync_group(
        group.id, NodeSyncGroupUpdate(primary_node_id=2, replica_node_ids=[1]), ADMIN, db
    )

    db.refresh(old)
    db.refresh(new)
    assert old.sync_group_id is None
    assert new.sync_group_id == group.id


def test_rename_keeps_existing_links(db):
    group = _group(db, sync_mode="auto", primary=1, replicas=(2,))
    primary = _config(db, 1, "alice", group_id=group.id)
    shadow = _config(db, 2, "alice", group_id=group.id, primary_id=primary.id)

    node_sync.update_sync_group(group.id, NodeSyncGroupUpdate(name="renamed"), ADMIN, db)

    db.refresh(shadow)
    assert shadow.ha_primary_config_id == primary.id
    assert shadow.sync_group_id == group.id
