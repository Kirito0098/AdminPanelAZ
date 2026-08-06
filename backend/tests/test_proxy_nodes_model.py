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
from app.services.node_manager import ACTIVE_NODE_KEY, get_active_node, set_active_node_id
from app.services import node_manager as node_manager_mod


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


def test_set_active_node_id_rejects_proxy(db):
    proxy = _add_node(db, name="proxy-guard", kind="proxy", port=9101)
    with pytest.raises(HTTPException) as exc:
        set_active_node_id(db, proxy.id)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Прокси-узел нельзя сделать активным для VPN"
    assert get_active_node_id_raw(db) in (None, "")


def test_set_active_node_id_allows_vpn(db):
    vpn = _add_node(db, name="vpn-guard", kind="vpn")
    set_active_node_id(db, vpn.id)
    db.commit()
    assert get_active_node(db).id == vpn.id


def test_get_active_node_skips_proxy(db, monkeypatch):
    proxy = _add_node(db, name="proxy-only", kind="proxy", port=9101)
    vpn = _add_node(db, name="vpn-b", kind="vpn")
    # Plant legacy/corrupt active_node_id (bypass guard) to verify recovery.
    node_manager_mod._set_setting(db, ACTIVE_NODE_KEY, str(proxy.id))
    db.commit()

    monkeypatch.setattr("app.services.node_manager.settings.local_antizapret_enabled", False)
    active = get_active_node(db)
    assert active.id == vpn.id
    assert active.node_kind == "vpn"


def get_active_node_id_raw(db) -> str | None:
    row = db.query(AppSetting).filter(AppSetting.key == ACTIVE_NODE_KEY).first()
    return None if row is None else row.value


def test_delete_active_node_fallback_skips_proxy(db, monkeypatch):
    """After deleting the active VPN node, fallback must not promote a proxy."""
    from app.routers import nodes as nodes_router
    from app.services.node_manager import get_active_node_id

    proxy = _add_node(db, name="proxy-fallback", kind="proxy", port=9101)
    vpn_active = _add_node(db, name="vpn-active", kind="vpn")
    vpn_other = _add_node(db, name="vpn-other", kind="vpn")
    set_active_node_id(db, vpn_active.id)
    db.commit()

    monkeypatch.setattr(nodes_router, "find_group_for_node", lambda _db, _id: None)
    monkeypatch.setattr(nodes_router, "purge_node_related", lambda _db, _id: None)
    monkeypatch.setattr(nodes_router, "sync_local_node", lambda _db: None)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)

    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    nodes_router.delete_node(vpn_active.id, request, admin=admin, db=db)

    assert get_active_node_id(db) == vpn_other.id
    assert db.query(Node).filter(Node.id == proxy.id).one().node_kind == "proxy"


def test_delete_active_node_clears_when_only_proxy_remains(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.services.node_manager import get_active_node_id

    _add_node(db, name="proxy-only-left", kind="proxy", port=9101)
    vpn_active = _add_node(db, name="vpn-last", kind="vpn")
    set_active_node_id(db, vpn_active.id)
    db.commit()

    monkeypatch.setattr(nodes_router, "find_group_for_node", lambda _db, _id: None)
    monkeypatch.setattr(nodes_router, "purge_node_related", lambda _db, _id: None)
    monkeypatch.setattr(nodes_router, "sync_local_node", lambda _db: None)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)

    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    nodes_router.delete_node(vpn_active.id, request, admin=admin, db=db)

    assert get_active_node_id(db) is None
