"""Удаление узла: связанные строки во всех таблицах со ссылкой на nodes.id не дают 409."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Boolean, DateTime, Float, Integer, create_engine, event, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app import database
from app.database import Base
from app.models import Node, NodeStatus, OpenVpnBufferGuardSettings
from app.services import openvpn_buffer_guard_worker as guard_worker
from app.services.node_manager import purge_node_related

LOCAL_ID, VICTIM_ID, OTHER_ID = 1, 2, 3
# Узел в HA-группе удалить нельзя (маршрут отвечает 409 до purge), поэтому группы здесь не участвуют.
_NOT_PURGED = {("nodes", "linked_vpn_node_id"), ("node_sync_groups", "primary_node_id")}


@pytest.fixture()
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'adminpanel.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        database.apply_sqlite_connection_pragmas(dbapi_connection.cursor())

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for node_id, name, is_local in ((LOCAL_ID, "local", True), (VICTIM_ID, "victim", False), (OTHER_ID, "other", False)):
        session.add(
            Node(id=node_id, name=name, host=f"10.0.0.{node_id}", is_local=is_local, status=NodeStatus.online)
        )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _node_fk_columns() -> list[tuple[str, str]]:
    return sorted(
        (fk.parent.table.name, fk.parent.name)
        for table in Base.metadata.sorted_tables
        for fk in table.foreign_keys
        if fk.column.table.name == "nodes"
    )


def _dummy(column) -> object:
    if isinstance(column.type, Boolean):
        return 0
    if isinstance(column.type, (Integer, Float)):
        return 1
    if isinstance(column.type, DateTime):
        return "2026-09-01 00:00:00"
    return f"x-{column.table.name}-{column.name}"


def _insert_row(db, table_name: str, node_column: str, node_id: int) -> None:
    table = Base.metadata.tables[table_name]
    values = {
        column.name: _dummy(column)
        for column in table.columns
        if not column.primary_key and not column.nullable
    }
    values[node_column] = node_id
    names = ", ".join(values)
    params = ", ".join(f":{name}" for name in values)
    # Остальные внешние ключи (пользователь, код и т. п.) в этом тесте не важны.
    db.execute(text("PRAGMA foreign_keys=OFF"))
    db.execute(text(f"INSERT INTO {table_name} ({names}) VALUES ({params})"), values)
    db.commit()
    db.execute(text("PRAGMA foreign_keys=ON"))


def _delete_via_route(db, monkeypatch, node_id: int):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "find_group_for_node", lambda _db, _id: None)
    monkeypatch.setattr(nodes_router, "sync_local_node", lambda _db: None)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: MagicMock())
    return nodes_router.delete_node(node_id, MagicMock(), admin=SimpleNamespace(id=1, username="admin"), db=db)


def _count(db, sql: str, **params) -> int:
    return db.execute(text(sql), params).scalar_one()


def test_delete_node_with_rows_in_every_referencing_table(db, monkeypatch):
    covered = [fk for fk in _node_fk_columns() if fk not in _NOT_PURGED]
    assert ("openvpn_buffer_guard_settings", "node_id") in covered
    for table_name, column in covered:
        _insert_row(db, table_name, column, VICTIM_ID)

    resp = _delete_via_route(db, monkeypatch, VICTIM_ID)

    assert "удалён" in resp.message
    assert db.get(Node, VICTIM_ID) is None
    leftovers = {
        f"{table_name}.{column}": _count(db, f"SELECT COUNT(*) FROM {table_name} WHERE {column} = :n", n=VICTIM_ID)
        for table_name, column in covered
    }
    assert {key: value for key, value in leftovers.items() if value} == {}


def test_purge_keeps_rows_of_other_nodes(db):
    for table_name, column in _node_fk_columns():
        if (table_name, column) not in _NOT_PURGED:
            _insert_row(db, table_name, column, OTHER_ID)

    purge_node_related(db, VICTIM_ID)
    db.commit()

    for table_name, column in _node_fk_columns():
        if (table_name, column) not in _NOT_PURGED:
            assert _count(db, f"SELECT COUNT(*) FROM {table_name} WHERE {column} = :n", n=OTHER_ID) == 1, table_name


def test_owner_redemptions_move_to_remaining_node(db):
    db.execute(text("PRAGMA foreign_keys=OFF"))
    db.execute(
        text(
            "INSERT INTO unlock_code_redemptions (id, code_id, user_id, client_name, node_id, redeemed_at) VALUES "
            "(1, 7, 5, 'alice', :victim, '2026-09-01'), "
            "(2, 7, NULL, 'bob', :victim, '2026-09-01'), "
            "(3, 7, NULL, 'carol', :other, '2026-09-01')"
        ),
        {"victim": VICTIM_ID, "other": OTHER_ID},
    )
    db.commit()
    db.execute(text("PRAGMA foreign_keys=ON"))

    purge_node_related(db, VICTIM_ID)
    db.commit()

    rows = db.execute(text("SELECT id, user_id, node_id FROM unlock_code_redemptions ORDER BY id")).all()
    # Повторное погашение того же кода владельцем проверяется по (код, пользователь) — запись должна остаться.
    assert [tuple(r) for r in rows] == [(1, 5, LOCAL_ID), (3, None, OTHER_ID)]


def test_guard_worker_does_not_create_settings_rows(db):
    assert guard_worker._online_nodes_with_enabled_settings(db) == []
    assert db.query(OpenVpnBufferGuardSettings).count() == 0

    db.add(OpenVpnBufferGuardSettings(node_id=OTHER_ID, enabled=True))
    db.add(OpenVpnBufferGuardSettings(node_id=VICTIM_ID, enabled=False))
    db.commit()

    assert [node.id for node in guard_worker._online_nodes_with_enabled_settings(db)] == [OTHER_ID]
    assert db.query(OpenVpnBufferGuardSettings).count() == 2
