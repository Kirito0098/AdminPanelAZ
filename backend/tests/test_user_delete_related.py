"""Удаление пользователя: строки во всех таблицах со ссылкой на users.id не дают 500."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Boolean, DateTime, Float, Integer, create_engine, event, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app import database
from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnConfig

ADMIN_ID, VICTIM_ID = 1, 2


@pytest.fixture()
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'adminpanel.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        database.apply_sqlite_connection_pragmas(dbapi_connection.cursor())

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=ADMIN_ID, username="admin", password_hash="x", role=UserRole.admin, is_active=True))
    session.add(User(id=VICTIM_ID, username="victim", password_hash="x", role=UserRole.user, is_active=True))
    session.add(Node(id=1, name="local", host="127.0.0.1", is_local=True, status=NodeStatus.online))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user_fk_columns() -> list[tuple[str, str]]:
    return sorted(
        (fk.parent.table.name, fk.parent.name)
        for table in Base.metadata.sorted_tables
        for fk in table.foreign_keys
        if fk.column.table.name == "users"
    )


def _dummy(column, tag: str) -> object:
    if isinstance(column.type, Boolean):
        return 0
    if isinstance(column.type, (Integer, Float)):
        return 1
    if isinstance(column.type, DateTime):
        return "2026-09-01 00:00:00"
    return f"x-{column.name}-{tag}"


def _insert_row(db, table_name: str, user_column: str, user_id: int) -> None:
    table = Base.metadata.tables[table_name]
    values = {
        column.name: _dummy(column, f"{user_column}-{user_id}")
        for column in table.columns
        if not column.primary_key and not column.nullable
    }
    values[user_column] = user_id
    names = ", ".join(values)
    params = ", ".join(f":{name}" for name in values)
    # Остальные внешние ключи (узел, код и т. п.) и CHECK-ограничения в этом тесте не важны.
    db.execute(text("PRAGMA foreign_keys=OFF"))
    db.execute(text("PRAGMA ignore_check_constraints=ON"))
    db.execute(text(f"INSERT INTO {table_name} ({names}) VALUES ({params})"), values)
    db.commit()
    db.execute(text("PRAGMA ignore_check_constraints=OFF"))
    db.execute(text("PRAGMA foreign_keys=ON"))


def _delete_via_route(db, monkeypatch, user_id: int):
    from app.routers import users as users_router

    monkeypatch.setattr(users_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(users_router.admin_notify_service, "send_user_delete", lambda *_a, **_k: None)
    admin = db.get(User, ADMIN_ID)
    return users_router.delete_user(user_id, MagicMock(), db=db, current_user=admin)


def test_delete_user_with_rows_in_every_referencing_table(db, monkeypatch):
    covered = _user_fk_columns()
    assert ("unlock_code_redemptions", "user_id") in covered
    for table_name, column in covered:
        _insert_row(db, table_name, column, VICTIM_ID)

    resp = _delete_via_route(db, monkeypatch, VICTIM_ID)

    assert resp.message == "Пользователь удалён"
    assert db.get(User, VICTIM_ID) is None
    leftovers = {
        f"{table_name}.{column}": db.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE {column} = :u"), {"u": VICTIM_ID}
        ).scalar_one()
        for table_name, column in covered
    }
    assert {key: value for key, value in leftovers.items() if value} == {}


def test_delete_user_hands_configs_to_admin_and_keeps_created_rows(db, monkeypatch):
    db.add(VpnConfig(node_id=1, client_name="alice", vpn_type="openvpn", owner_id=VICTIM_ID))
    db.commit()
    _insert_row(db, "unlock_codes", "created_by_user_id", VICTIM_ID)

    _delete_via_route(db, monkeypatch, VICTIM_ID)

    assert db.query(VpnConfig).one().owner_id == ADMIN_ID
    # Созданный удалённым пользователем код остаётся, без автора.
    assert db.execute(text("SELECT created_by_user_id FROM unlock_codes")).all() == [(None,)]


def test_admin_rows_untouched(db, monkeypatch):
    _insert_row(db, "unlock_codes", "created_by_user_id", ADMIN_ID)

    _delete_via_route(db, monkeypatch, VICTIM_ID)

    assert db.execute(text("SELECT created_by_user_id FROM unlock_codes")).all() == [(ADMIN_ID,)]
