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
from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus, User, UserRole
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
