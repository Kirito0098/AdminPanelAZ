from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus
from app.schemas import NodeCreate, ProxyDestinationBody
from app.services.feature_guards import module_disabled_message
from app.services.feature_toggles import FeatureToggleService, is_nodes_enabled


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


def _add_node(db, *, name: str, kind: str = "vpn") -> Node:
    node = Node(
        name=name,
        host="10.0.0.1",
        port=9100,
        api_key_hash="hash",
        api_key_encrypted="enc",
        is_local=False,
        node_kind=kind,
        status=NodeStatus.unknown,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def test_is_nodes_enabled_defaults_true(env_file: Path, monkeypatch):
    svc = _svc(env_file)
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: svc,
    )
    assert is_nodes_enabled(None) is True
    env_file.write_text("FEATURE_NODES_ENABLED=false\n", encoding="utf-8")
    svc._invalidate_env_map()
    assert is_nodes_enabled(None) is False


def test_require_nodes_module_blocks_when_disabled(monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: False)
    with pytest.raises(HTTPException) as exc:
        nodes_router._require_nodes_module(MagicMock())
    assert exc.value.status_code == 403
    assert exc.value.detail == module_disabled_message("nodes")


@pytest.mark.parametrize("node_kind", ["vpn", "proxy"])
def test_create_node_blocked_when_nodes_disabled(db, monkeypatch, node_kind):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: False)
    monkeypatch.setattr(
        nodes_router,
        "validate_node_host",
        lambda _host: (_ for _ in ()).throw(AssertionError("host validation should not run")),
    )
    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    payload = NodeCreate(
        name="node-1",
        host="1.2.3.4",
        api_key="secret-key-1",
        node_kind=node_kind,
    )
    with pytest.raises(HTTPException) as exc:
        nodes_router.create_node(payload, request, admin=admin, db=db)
    assert exc.value.status_code == 403
    assert exc.value.detail == module_disabled_message("nodes")


def test_proxy_destination_blocked_when_nodes_disabled(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: False)
    monkeypatch.setattr(
        nodes_router,
        "_require_proxy_node",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("proxy lookup should not run")),
    )
    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    payload = ProxyDestinationBody(destination_ip="1.2.3.4")
    with pytest.raises(HTTPException) as exc:
        nodes_router.put_proxy_destination(1, payload, request, admin=admin, db=db)
    assert exc.value.status_code == 403
    assert exc.value.detail == module_disabled_message("nodes")


def test_health_check_stays_enabled_when_nodes_disabled(db, monkeypatch):
    from app.routers import nodes as nodes_router

    node = _add_node(db, name="vpn-health")
    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: False)
    monkeypatch.setattr(nodes_router, "check_node_health", lambda *_args, **_kwargs: {"status": "online"})
    monkeypatch.setattr(nodes_router, "update_node_from_health", lambda *_args, **_kwargs: None)
    result = nodes_router.health_check(node.id, MagicMock(), db=db)
    assert result.node_id == node.id
