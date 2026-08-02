"""Proxy nodes wave 1: feature toggle, node_kind model, activate/create guards."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSetting, Node, NodeStatus
from app.schemas import NodeCreate
from app.services.feature_toggles import FEATURE_TOGGLE_BY_KEY, FeatureToggleService, is_proxy_nodes_enabled
from app.services.node_manager import get_active_node, set_active_node_id


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")
    return path


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


def _svc(env_file: Path, **flags: bool) -> FeatureToggleService:
    lines = [f"{key}={'true' if value else 'false'}" for key, value in flags.items()]
    env_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return FeatureToggleService(env_file)


def _add_node(db, *, name: str, kind: str = "vpn", is_local: bool = False, port: int = 9100) -> Node:
    node = Node(
        name=name,
        host="10.0.0.1",
        port=port,
        api_key_hash="hash",
        api_key_encrypted="enc",
        is_local=is_local,
        node_kind=kind,
        status=NodeStatus.unknown,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def test_proxy_nodes_toggle_defaults_false(env_file: Path):
    assert "proxy_nodes" in FEATURE_TOGGLE_BY_KEY
    definition = FEATURE_TOGGLE_BY_KEY["proxy_nodes"]
    assert definition.env_key == "FEATURE_PROXY_NODES_ENABLED"
    assert definition.default is False
    assert definition.group == "app_module"
    svc = _svc(env_file)
    assert svc.is_enabled("proxy_nodes") is False


def test_proxy_nodes_toggle_can_enable(env_file: Path):
    svc = _svc(env_file, FEATURE_PROXY_NODES_ENABLED=True)
    assert svc.is_enabled("proxy_nodes") is True


def test_is_proxy_nodes_enabled_helper(env_file: Path, monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: _svc(env_file, FEATURE_PROXY_NODES_ENABLED=False),
    )
    assert is_proxy_nodes_enabled(None) is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: _svc(env_file, FEATURE_PROXY_NODES_ENABLED=True),
    )
    assert is_proxy_nodes_enabled(None) is True


def test_create_proxy_blocked_when_toggle_off(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_proxy_nodes_enabled", lambda _db: False)
    monkeypatch.setattr(nodes_router, "validate_node_host", lambda host: host)
    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    payload = NodeCreate(
        name="proxy-1",
        host="1.2.3.4",
        api_key="secret-key-1",
        node_kind="proxy",
    )
    with pytest.raises(HTTPException) as exc:
        nodes_router.create_node(payload, request, admin=admin, db=db)
    assert exc.value.status_code == 403
    assert "Прокси-узлы" in str(exc.value.detail)


def test_create_proxy_ok_when_toggle_on(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_proxy_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "validate_node_host", lambda host: host)
    monkeypatch.setattr(nodes_router, "store_api_key", lambda _h, key: ("hash", "enc"))
    monkeypatch.setattr(nodes_router, "check_node_health", lambda *a, **k: {"status": "online"})
    monkeypatch.setattr(nodes_router, "update_node_from_health", lambda *a, **k: None)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)

    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    payload = NodeCreate(
        name="proxy-1",
        host="1.2.3.4",
        api_key="secret-key-1",
        node_kind="proxy",
    )
    resp = nodes_router.create_node(payload, request, admin=admin, db=db)
    assert resp.node_kind == "proxy"
    assert resp.port == 9101
    assert resp.is_local is False
    stored = db.query(Node).filter(Node.id == resp.id).one()
    assert stored.node_kind == "proxy"
    assert stored.port == 9101
    # Must not become active VPN node
    active = db.query(AppSetting).filter(AppSetting.key == "active_node_id").first()
    assert active is None or active.value in ("", None)


def test_activate_proxy_rejected(db, monkeypatch):
    from app.routers import nodes as nodes_router

    proxy = _add_node(db, name="proxy-a", kind="proxy", port=9101)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    with pytest.raises(HTTPException) as exc:
        nodes_router.activate_node(proxy.id, request, admin=admin, db=db)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Прокси-узел нельзя сделать активным для VPN"


def test_activate_vpn_ok(db, monkeypatch):
    from app.routers import nodes as nodes_router

    vpn = _add_node(db, name="vpn-a", kind="vpn")
    monkeypatch.setattr(nodes_router, "check_node_health", lambda *a, **k: {"status": "online"})
    monkeypatch.setattr(nodes_router, "update_node_from_health", lambda *a, **k: None)
    monkeypatch.setattr(nodes_router, "_active_node_response", lambda _db, node: {"node_id": node.id})
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)

    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    result = nodes_router.activate_node(vpn.id, request, admin=admin, db=db)
    assert result["node_id"] == vpn.id
    assert get_active_node(db).id == vpn.id


def test_get_active_node_skips_proxy(db, monkeypatch):
    proxy = _add_node(db, name="proxy-only", kind="proxy", port=9101)
    vpn = _add_node(db, name="vpn-b", kind="vpn")
    set_active_node_id(db, proxy.id)
    db.commit()

    monkeypatch.setattr("app.services.node_manager.settings.local_antizapret_enabled", False)
    active = get_active_node(db)
    assert active.id == vpn.id
    assert active.node_kind == "vpn"
