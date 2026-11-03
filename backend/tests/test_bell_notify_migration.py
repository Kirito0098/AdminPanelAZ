"""Миграция колонки подписки: добавляет users.bell_notify_categories и переживает повторный запуск."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text

from app import database
from app.database import Base
from app.models import AdminPanelNotificationState  # noqa: F401  — регистрирует таблицы в Base.metadata

COLUMN = "bell_notify_categories"


@pytest.fixture()
def file_engine(tmp_path: Path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'adminpanel.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        database.apply_sqlite_connection_pragmas(dbapi_connection.cursor())

    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


def test_migration_adds_bell_categories_column(file_engine):
    with file_engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE users DROP COLUMN {COLUMN}"))

    database._migrate_users_bell_notify_categories()
    database._migrate_users_bell_notify_categories()  # повторный запуск не должен падать

    columns = {col["name"] for col in inspect(file_engine).get_columns("users")}
    assert COLUMN in columns
