"""Node.portal_label: client-facing node name for the user portal."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base
from app.models import Node, NodeStatus
from app.schemas import NodeUpdate


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


def _add_node(db, *, name: str = "vpn-a", is_local: bool = False) -> Node:
    node = Node(
        name=name,
        host="10.0.0.1",
        port=9100,
        api_key_hash="hash",
        api_key_encrypted="enc",
        is_local=is_local,
        node_kind="vpn",
        status=NodeStatus.unknown,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _update(db, node_id: int, payload: NodeUpdate, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "_require_nodes_module", lambda _db: None)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    return nodes_router.update_node(
        node_id,
        payload,
        MagicMock(),
        admin=SimpleNamespace(id=1, username="admin"),
        db=db,
    )


def test_update_sets_and_strips_portal_label(db, monkeypatch):
    node = _add_node(db)
    resp = _update(db, node.id, NodeUpdate(portal_label="  Нидерланды  "), monkeypatch)
    assert resp.portal_label == "Нидерланды"
    db.refresh(node)
    assert node.portal_label == "Нидерланды"


def test_update_blank_or_null_clears_portal_label(db, monkeypatch):
    node = _add_node(db)
    _update(db, node.id, NodeUpdate(portal_label="NL"), monkeypatch)
    assert _update(db, node.id, NodeUpdate(portal_label="   "), monkeypatch).portal_label is None
    _update(db, node.id, NodeUpdate(portal_label="NL"), monkeypatch)
    assert _update(db, node.id, NodeUpdate(portal_label=None), monkeypatch).portal_label is None


def test_update_without_field_keeps_portal_label(db, monkeypatch):
    node = _add_node(db)
    _update(db, node.id, NodeUpdate(portal_label="NL"), monkeypatch)
    resp = _update(db, node.id, NodeUpdate(name="vpn-renamed"), monkeypatch)
    assert resp.portal_label == "NL"
    assert resp.name == "vpn-renamed"


def test_update_local_node_portal_label(db, monkeypatch):
    node = _add_node(db, name="local", is_local=True)
    resp = _update(db, node.id, NodeUpdate(portal_label="Москва"), monkeypatch)
    assert resp.portal_label == "Москва"


def test_portal_label_too_long_rejected():
    with pytest.raises(ValueError):
        NodeUpdate(portal_label="x" * 129)


def test_migration_adds_portal_label(tmp_path: Path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE nodes (id INTEGER PRIMARY KEY, name VARCHAR(128))"))
    monkeypatch.setattr(database, "engine", engine)

    database._migrate_nodes_portal_label()
    database._migrate_nodes_portal_label()

    cols = {col["name"] for col in inspect(engine).get_columns("nodes")}
    assert "portal_label" in cols
    engine.dispose()
