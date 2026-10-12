"""Deep health and the active node response must not leak infrastructure details to outsiders."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database_module
from app.auth import create_access_token
from app.database import Base
from app.models import Node, NodeStatus, User, UserRole
from app.routers import nodes as nodes_router
from app.services import openapi_docs_gate
from app.services.health_checks import assert_health_deep_access


@pytest.fixture
def session_factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all(
        [
            User(username="admin", password_hash="x", role=UserRole.admin, is_active=True),
            User(username="alice", password_hash="x", role=UserRole.user, is_active=True),
        ]
    )
    db.commit()
    db.close()
    monkeypatch.setattr(database_module, "SessionLocal", factory)
    monkeypatch.setattr(openapi_docs_gate, "SessionLocal", factory)
    yield factory
    engine.dispose()


def _request(client_host: str, *, token: str | None = None, forwarded_for: str | None = None):
    headers = {}
    if token:
        headers["authorization"] = f"Bearer {token}"
    if forwarded_for:
        headers["x-forwarded-for"] = forwarded_for
    return SimpleNamespace(client=SimpleNamespace(host=client_host), headers=headers)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_deep_health_allows_loopback(session_factory, host):
    assert_health_deep_access(_request(host))


def test_deep_health_rejects_external_client(session_factory):
    with pytest.raises(HTTPException) as exc_info:
        assert_health_deep_access(_request("203.0.113.9"))
    assert exc_info.value.status_code == 403


def test_deep_health_rejects_external_client_behind_local_proxy(session_factory):
    with pytest.raises(HTTPException):
        assert_health_deep_access(_request("127.0.0.1", forwarded_for="203.0.113.9"))


def test_deep_health_rejects_non_admin_token(session_factory):
    with pytest.raises(HTTPException):
        assert_health_deep_access(_request("203.0.113.9", token=create_access_token({"sub": "alice"})))


def test_deep_health_allows_admin_token(session_factory):
    assert_health_deep_access(_request("203.0.113.9", token=create_access_token({"sub": "admin"})))


def _node() -> Node:
    now = datetime.utcnow()
    return Node(
        id=1,
        name="remote",
        host="10.0.0.2",
        port=9100,
        node_kind="vpn",
        status=NodeStatus.online,
        is_local=False,
        ssh_host="198.51.100.5",
        ssh_port=2222,
        ssh_username="root",
        ssh_private_key_encrypted="enc",
        ssh_remote_agent_host="127.0.0.1",
        ssh_remote_agent_port=9100,
        destination_ip="198.51.100.6",
        node_metadata=json.dumps({"server_ip": "198.51.100.7"}),
        created_at=now,
        updated_at=now,
    )


def test_active_node_hides_infra_details_from_non_admin(monkeypatch):
    monkeypatch.setattr(nodes_router, "build_ha_node_context", lambda db, node_id: None)
    user = SimpleNamespace(role=UserRole.user)

    node = nodes_router._active_node_response(None, _node(), user).node

    assert node.name == "remote"
    assert node.status == NodeStatus.online
    assert node.ssh_host is None
    assert node.ssh_username is None
    assert node.ssh_key_configured is False
    assert node.ssh_remote_agent_host is None
    assert node.ssh_remote_agent_port is None
    assert node.destination_ip is None
    assert node.metadata == {}


def test_active_node_keeps_infra_details_for_admin(monkeypatch):
    monkeypatch.setattr(nodes_router, "build_ha_node_context", lambda db, node_id: None)
    admin = SimpleNamespace(role=UserRole.admin)

    node = nodes_router._active_node_response(None, _node(), admin).node

    assert node.ssh_host == "198.51.100.5"
    assert node.destination_ip == "198.51.100.6"
    assert node.metadata == {"server_ip": "198.51.100.7"}
