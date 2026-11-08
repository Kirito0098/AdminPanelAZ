"""Mini App nodes: HA role is visible and an HA replica cannot be activated.

Регрессия: раньше `/tg-mini/nodes` не отдавал HA-роль, а активация реплики
проходила без проверки, из-за чего конфиги можно было создавать «не на том»
сервере. Теперь роль видна, а активация реплики → 403.
"""

import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_tg_mini_user
from app.database import Base, get_db
from app.models import (
    Node,
    NodeStatus,
    NodeSyncGroup,
    SyncStatus,
    User,
    UserRole,
)
from app.routers.tg_mini.nodes import router as nodes_router


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def admin(db):
    user = User(
        username="admin",
        password_hash="x",
        role=UserRole.admin,
        is_active=True,
        panel_login_enabled=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def ha_nodes(db):
    primary = Node(
        name="Primary",
        host="127.0.0.1",
        port=9100,
        api_key_hash="h",
        api_key_encrypted="e",
        status=NodeStatus.online,
        is_local=True,
        node_kind="vpn",
        node_metadata="{}",
    )
    replica = Node(
        name="Replica",
        host="127.0.0.2",
        port=9100,
        api_key_hash="h",
        api_key_encrypted="e",
        status=NodeStatus.online,
        is_local=False,
        node_kind="vpn",
        node_metadata="{}",
    )
    db.add_all([primary, replica])
    db.commit()
    db.refresh(primary)
    db.refresh(replica)
    group = NodeSyncGroup(
        name="ha",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=json.dumps([replica.id]),
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    db.add(group)
    db.commit()
    return primary, replica


@pytest.fixture()
def client(db, admin, ha_nodes):
    app = FastAPI()
    app.include_router(nodes_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_tg_mini_user] = lambda: admin
    with (
        patch("app.routers.tg_mini.nodes.sync_local_node", lambda *_a, **_k: None),
        patch("app.routers.tg_mini.nodes.check_node_health", lambda *_a, **_k: {"ok": True}),
        patch("app.routers.tg_mini.nodes.update_node_from_health", lambda *_a, **_k: None),
    ):
        yield TestClient(app)


def test_nodes_expose_ha_role(client, ha_nodes):
    primary, replica = ha_nodes

    resp = client.get("/nodes")

    assert resp.status_code == 200
    by_id = {node["id"]: node for node in resp.json()["nodes"]}
    assert by_id[primary.id]["ha_role"] == "primary"
    assert by_id[replica.id]["ha_role"] == "replica"
    assert by_id[replica.id]["ha_primary_name"] == primary.name


def test_replica_cannot_be_activated(client, ha_nodes):
    _, replica = ha_nodes

    resp = client.post(f"/nodes/{replica.id}/activate")

    assert resp.status_code == 403
    assert "replica" in resp.json()["detail"].lower()


def test_primary_can_be_activated(client, ha_nodes):
    primary, _ = ha_nodes

    resp = client.post(f"/nodes/{primary.id}/activate")

    assert resp.status_code == 200
    assert resp.json()["node"]["ha_role"] == "primary"
