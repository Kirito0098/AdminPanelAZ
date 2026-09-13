"""API tests for node transport list + PATCH."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus
from app.schemas import NodeTransportUpdate


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _add_node(db, *, name: str = "n1", kind: str = "vpn", transport: str = "http") -> Node:
    node = Node(
        name=name,
        host="10.0.0.1",
        port=9100 if kind == "vpn" else 9101,
        api_key_hash="hash",
        api_key_encrypted="enc",
        is_local=False,
        transport=transport,
        mtls_enabled=(transport == "mtls"),
        node_kind=kind,
        status=NodeStatus.unknown,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def test_list_node_transports():
    from app.routers import nodes as nodes_router

    resp = nodes_router.list_node_transports(SimpleNamespace())
    ids = [i.id for i in resp.items]
    assert ids == ["http", "mtls", "ssh"]
    by_id = {i.id: i for i in resp.items}
    assert by_id["ssh"].available is False
    assert by_id["http"].available is True


def test_patch_transport_ssh_returns_400_without_db_write(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db, transport="http")
    admin = SimpleNamespace(id=1, username="admin")

    with pytest.raises(HTTPException) as exc:
        nodes_router.patch_node_transport(
            node.id,
            NodeTransportUpdate(transport="ssh"),
            admin=admin,
            db=db,
        )
    assert exc.value.status_code == 400
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "transport_not_implemented"

    db.refresh(node)
    assert node.transport == "http"
    assert node.mtls_enabled is False


def test_patch_transport_proxy_http_to_mtls(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db, kind="proxy", transport="http")
    admin = SimpleNamespace(id=1, username="admin")

    def _fake_enable(db_session, n, actor):
        n.transport = "mtls"
        n.mtls_enabled = True
        db_session.add(n)
        db_session.commit()
        db_session.refresh(n)
        return n

    monkeypatch.setattr(nodes_router, "enable_mtls", _fake_enable)

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(transport="mtls"),
        admin=admin,
        db=db,
    )
    assert resp.transport == "mtls"
    assert resp.mtls_enabled is True
    db.refresh(node)
    assert node.transport == "mtls"


def test_patch_transport_noop_same_value(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db, transport="http")
    admin = SimpleNamespace(id=1, username="admin")
    enable = MagicMock()
    monkeypatch.setattr(nodes_router, "enable_mtls", enable)

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(transport="http"),
        admin=admin,
        db=db,
    )
    assert resp.transport == "http"
    enable.assert_not_called()


def test_patch_transport_drops_ssh_tunnel_when_switching_to_http(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    node = _add_node(db, transport="ssh")
    admin = SimpleNamespace(id=1, username="admin")
    pool = MagicMock()
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: pool)

    def _fake_disable(db_session, n, actor):
        n.transport = "http"
        n.mtls_enabled = False
        db_session.add(n)
        db_session.commit()
        db_session.refresh(n)
        return n

    monkeypatch.setattr(nodes_router, "disable_mtls", _fake_disable)

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(transport="http"),
        admin=admin,
        db=db,
    )
    assert resp.transport == "http"
    pool.drop.assert_called_once_with(node.id)


def test_patch_transport_local_rejected(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db)
    node.is_local = True
    db.add(node)
    db.commit()
    admin = SimpleNamespace(id=1, username="admin")

    with pytest.raises(HTTPException) as exc:
        nodes_router.patch_node_transport(
            node.id,
            NodeTransportUpdate(transport="mtls"),
            admin=admin,
            db=db,
        )
    assert exc.value.status_code == 400


def test_to_response_derives_mtls_from_transport(db):
    from app.routers import nodes as nodes_router

    node = _add_node(db, transport="mtls")
    resp = nodes_router._to_response(node)
    assert resp.transport == "mtls"
    assert resp.mtls_enabled is True


def test_delete_node_drops_ssh_tunnel(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "find_group_for_node", lambda _db, _id: None)
    monkeypatch.setattr(nodes_router, "sync_local_node", lambda _db: None)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    pool = MagicMock()
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: pool)
    node = _add_node(db, transport="ssh")
    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()

    resp = nodes_router.delete_node(node.id, request, admin=admin, db=db)

    assert "удалён" in resp.message
    pool.drop.assert_called_once_with(node.id)
