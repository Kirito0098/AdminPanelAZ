"""Built-in client templates are seeded once per node; deleted ones do not come back on restart."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base
from app.models import ClientTemplate, Node, VpnType


@pytest.fixture()
def seed_engine(tmp_path: Path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


def _add_node(engine, name: str) -> int:
    with sessionmaker(bind=engine)() as db:
        node = Node(name=name, host="10.0.0.1", node_metadata="{}")
        db.add(node)
        db.commit()
        return node.id


def _template_names(engine, node_id: int) -> list[str]:
    with sessionmaker(bind=engine)() as db:
        return sorted(
            row.name for row in db.query(ClientTemplate).filter(ClientTemplate.node_id == node_id).all()
        )


def _seeded(engine, node_id: int) -> bool:
    with sessionmaker(bind=engine)() as db:
        return bool(db.get(Node, node_id).client_templates_seeded)


def test_deleted_builtin_templates_do_not_come_back(seed_engine):
    node_id = _add_node(seed_engine, "vpn-a")

    database._seed_client_templates_for_nodes()
    builtins = _template_names(seed_engine, node_id)
    assert builtins
    assert _seeded(seed_engine, node_id) is True

    with sessionmaker(bind=seed_engine)() as db:
        db.query(ClientTemplate).filter(ClientTemplate.node_id == node_id).delete()
        db.commit()
    database._seed_client_templates_for_nodes()

    assert _template_names(seed_engine, node_id) == []


def test_new_node_gets_builtins_once(seed_engine):
    first = _add_node(seed_engine, "vpn-a")
    database._seed_client_templates_for_nodes()
    second = _add_node(seed_engine, "vpn-b")

    database._seed_client_templates_for_nodes()
    database._seed_client_templates_for_nodes()

    assert _template_names(seed_engine, second) == _template_names(seed_engine, first)


def test_node_with_templates_before_upgrade_gets_no_builtins(seed_engine):
    node_id = _add_node(seed_engine, "vpn-a")
    with sessionmaker(bind=seed_engine)() as db:
        db.add(ClientTemplate(node_id=node_id, name="Мой шаблон", vpn_type=VpnType.openvpn))
        db.commit()

    database._seed_client_templates_for_nodes()

    assert _template_names(seed_engine, node_id) == ["Мой шаблон"]
    assert _seeded(seed_engine, node_id) is True


def test_migration_adds_client_templates_seeded(tmp_path: Path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE nodes (id INTEGER PRIMARY KEY, name VARCHAR(128))"))
        conn.execute(text("INSERT INTO nodes (id, name) VALUES (1, 'old')"))
    monkeypatch.setattr(database, "engine", engine)

    database._migrate_nodes_client_templates_seeded()
    database._migrate_nodes_client_templates_seeded()

    with engine.connect() as conn:
        value = conn.execute(text("SELECT client_templates_seeded FROM nodes WHERE id = 1")).scalar_one()
    assert value == 0
    engine.dispose()
