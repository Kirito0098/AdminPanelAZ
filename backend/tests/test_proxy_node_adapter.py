"""ProxyNodeAdapter + panel proxy API (MagicMock, no live net)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus
from app.schemas import ProxyDestinationBody
from app.services.node_manager import get_adapter_for_node, get_proxy_adapter
from app.services.proxy_node_adapter import ProxyNodeAdapter


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


def _add_node(db, *, name: str = "proxy1", kind: str = "proxy", port: int = 9101) -> Node:
    node = Node(
        name=name,
        host="10.0.0.9",
        port=port,
        api_key_hash="hash",
        api_key_encrypted="enc",
        is_local=False,
        node_kind=kind,
        status=NodeStatus.unknown,
        node_metadata="{}",
        destination_ip=None,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def test_proxy_adapter_health_status_destination_mappings():
    adapter = ProxyNodeAdapter("10.0.0.9", 9101, "k" * 32, mtls_enabled=False)
    with patch.object(adapter, "_request") as req:
        req.side_effect = [
            {"ok": True, "version": "0.1.0"},
            {"installed": True, "destination_ip": "1.2.3.4", "detail": None},
            {"installed": True, "destination_ip": "5.6.7.8", "detail": None},
            {"mappings": [{"client_ip": "9.9.9.9", "client_port": 1234}]},
        ]
        assert adapter.health()["ok"] is True
        assert adapter.proxy_status()["destination_ip"] == "1.2.3.4"
        assert adapter.set_destination("5.6.7.8")["destination_ip"] == "5.6.7.8"
        assert adapter.mappings()["mappings"][0]["client_ip"] == "9.9.9.9"
        assert req.call_args_list[0].args[:2] == ("GET", "/health")
        assert req.call_args_list[1].args[:2] == ("GET", "/proxy/status")
        assert req.call_args_list[2].args[:2] == ("PUT", "/proxy/destination")
        assert req.call_args_list[2].kwargs.get("json") == {"destination_ip": "5.6.7.8"}
        assert req.call_args_list[3].args[:2] == ("GET", "/proxy/mappings")


def test_get_proxy_adapter_rejects_vpn(db):
    node = _add_node(db, kind="vpn", port=9100)
    with pytest.raises(HTTPException) as exc:
        get_proxy_adapter(node)
    assert exc.value.status_code == 400


def test_get_adapter_for_node_rejects_proxy(db):
    node = _add_node(db, kind="proxy")
    with pytest.raises(HTTPException) as exc:
        get_adapter_for_node(node)
    assert exc.value.status_code == 400
    assert "прокси" in str(exc.value.detail).lower() or "VPN" in str(exc.value.detail)


def test_get_proxy_status_toggle_off(db, monkeypatch):
    from app.routers import nodes as nodes_router

    node = _add_node(db)
    admin = SimpleNamespace(id=1, username="admin")
    monkeypatch.setattr(nodes_router, "is_proxy_nodes_enabled", lambda _db: False)
    with pytest.raises(HTTPException) as exc:
        nodes_router.get_proxy_status(node.id, admin, db)
    assert exc.value.status_code == 403


def test_get_proxy_status_not_proxy(db, monkeypatch):
    from app.routers import nodes as nodes_router

    node = _add_node(db, kind="vpn", port=9100)
    admin = SimpleNamespace(id=1, username="admin")
    monkeypatch.setattr(nodes_router, "is_proxy_nodes_enabled", lambda _db: True)
    with pytest.raises(HTTPException) as exc:
        nodes_router.get_proxy_status(node.id, admin, db)
    assert exc.value.status_code == 404


def test_get_proxy_status_ok(db, monkeypatch):
    from app.routers import nodes as nodes_router

    node = _add_node(db)
    admin = SimpleNamespace(id=1, username="admin")
    monkeypatch.setattr(nodes_router, "is_proxy_nodes_enabled", lambda _db: True)
    adapter = MagicMock()
    adapter.proxy_status.return_value = {
        "installed": False,
        "destination_ip": None,
        "detail": "not found",
    }
    monkeypatch.setattr(nodes_router, "get_proxy_adapter", lambda _n: adapter)
    resp = nodes_router.get_proxy_status(node.id, admin, db)
    assert resp.installed is False
    assert resp.detail == "not found"


def test_put_proxy_destination_syncs_node(db, monkeypatch):
    from app.routers import nodes as nodes_router

    node = _add_node(db)
    monkeypatch.setattr(nodes_router, "is_proxy_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    adapter = MagicMock()
    adapter.set_destination.return_value = {
        "installed": True,
        "destination_ip": "8.8.8.8",
        "detail": None,
    }
    monkeypatch.setattr(nodes_router, "get_proxy_adapter", lambda _n: adapter)
    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    resp = nodes_router.put_proxy_destination(
        node.id,
        ProxyDestinationBody(destination_ip="8.8.8.8"),
        request,
        admin,
        db,
    )
    assert resp.destination_ip == "8.8.8.8"
    db.refresh(node)
    assert node.destination_ip == "8.8.8.8"
    adapter.set_destination.assert_called_once_with("8.8.8.8")


def test_refresh_proxy_status_syncs_destination(db, monkeypatch):
    from app.routers import nodes as nodes_router

    node = _add_node(db)
    admin = SimpleNamespace(id=1, username="admin")
    monkeypatch.setattr(nodes_router, "is_proxy_nodes_enabled", lambda _db: True)
    adapter = MagicMock()
    adapter.proxy_status.return_value = {
        "installed": True,
        "destination_ip": "1.1.1.1",
        "detail": None,
    }
    monkeypatch.setattr(nodes_router, "get_proxy_adapter", lambda _n: adapter)
    resp = nodes_router.refresh_proxy_status(node.id, admin, db)
    assert resp.destination_ip == "1.1.1.1"
    db.refresh(node)
    assert node.destination_ip == "1.1.1.1"


def test_get_proxy_mappings(db, monkeypatch):
    from app.routers import nodes as nodes_router

    node = _add_node(db)
    admin = SimpleNamespace(id=1, username="admin")
    monkeypatch.setattr(nodes_router, "is_proxy_nodes_enabled", lambda _db: True)
    adapter = MagicMock()
    adapter.mappings.return_value = {
        "mappings": [{"client_ip": "10.1.1.1", "client_port": 443}],
    }
    monkeypatch.setattr(nodes_router, "get_proxy_adapter", lambda _n: adapter)
    resp = nodes_router.get_proxy_mappings(node.id, admin, db)
    assert len(resp.mappings) == 1
    assert resp.mappings[0].client_ip == "10.1.1.1"


def test_check_node_health_uses_proxy_adapter(db, monkeypatch):
    from app.services import node_manager as nm

    node = _add_node(db)
    adapter = MagicMock()
    adapter.health.return_value = {"ok": True, "version": "0.1.0"}
    monkeypatch.setattr(nm, "get_proxy_adapter", lambda _n, api_key_override=None: adapter)
    health = nm.check_node_health(node)
    assert health["status"] == "online"
    assert health["ok"] is True
    adapter.health.assert_called_once()
