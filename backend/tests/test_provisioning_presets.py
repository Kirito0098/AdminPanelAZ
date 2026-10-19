"""Stage 2 Task 6: provisioning presets CRUD + node purge.

TDD: ожидаем FAIL до реализации сервиса, затем PASS.
Покрытие: единственность is_default, удаление node id из preset'ов при purge.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, ProvisioningPreset
from app.services.provisioning_presets import (
    create_preset,
    delete_preset,
    get_preset,
    list_presets,
    remove_node_from_presets,
    update_preset,
)


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


def test_only_one_default_preset(db):
    a = create_preset(db, name="A", node_ids=[1], protocols=["wireguard"], is_default=True)
    b = create_preset(db, name="B", node_ids=[1], protocols=["wireguard"], is_default=True)
    db.refresh(a)
    assert a.is_default is False and b.is_default is True


def test_purge_node_drops_id_from_presets(db):
    p = create_preset(db, name="P", node_ids=[10, 20], protocols=["wireguard"])
    removed = remove_node_from_presets(db, 10)
    db.refresh(p)
    assert removed == 1
    assert json.loads(p.node_ids) == [20]


def test_purge_unknown_node_changes_nothing(db):
    p = create_preset(db, name="P2", node_ids=[10, 20], protocols=["wireguard"])
    removed = remove_node_from_presets(db, 999)
    db.refresh(p)
    assert removed == 0
    assert json.loads(p.node_ids) == [10, 20]


def test_create_preset_defaults(db):
    p = create_preset(db, name="C", node_ids=[1], protocols=["wireguard"])
    assert p.id is not None
    assert p.config_count == 1
    assert p.config_quota is None
    assert p.traffic_limit_bytes is None
    assert p.access_days is None
    assert p.is_default is False
    assert json.loads(p.node_ids) == [1]
    assert json.loads(p.protocols) == ["wireguard"]


def test_update_preset_switches_default(db):
    a = create_preset(db, name="A", node_ids=[1], protocols=["wireguard"], is_default=True)
    b = create_preset(db, name="B", node_ids=[1], protocols=["wireguard"])
    row = update_preset(db, b.id, is_default=True)
    assert row is not None and row.is_default is True
    db.refresh(a)
    assert a.is_default is False


def test_update_preset_fields(db):
    p = create_preset(db, name="D", node_ids=[1], protocols=["wireguard"], config_count=2)
    row = update_preset(
        db,
        p.id,
        name="D2",
        node_ids=[1, 2],
        protocols=["openvpn", "wireguard"],
        config_count=3,
        config_quota=5,
        traffic_limit_bytes=10_000_000,
        access_days=30,
        is_default=True,
    )
    assert row is not None
    assert row.name == "D2"
    assert json.loads(row.node_ids) == [1, 2]
    assert json.loads(row.protocols) == ["openvpn", "wireguard"]
    assert row.config_count == 3
    assert row.config_quota == 5
    assert row.traffic_limit_bytes == 10_000_000
    assert row.access_days == 30
    assert row.is_default is True


def test_delete_preset(db):
    p = create_preset(db, name="E", node_ids=[1], protocols=["wireguard"])
    assert delete_preset(db, p.id) is True
    assert get_preset(db, p.id) is None
    assert delete_preset(db, 999999) is False


def test_list_presets_ordered(db):
    create_preset(db, name="B", node_ids=[1], protocols=["wireguard"])
    create_preset(db, name="A", node_ids=[1], protocols=["wireguard"])
    rows = list_presets(db)
    assert [row.name for row in rows] == ["B", "A"]  # порядок вставки = порядку id
