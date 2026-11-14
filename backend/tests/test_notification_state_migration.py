"""Миграция таблицы состояний уведомлений: создаёт схему и переживает повторный запуск."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text

from app import database
from app.database import Base
from app.models import AdminPanelNotificationState

# Модели регистрируют таблицы в Base.metadata при импорте — без этого create_all пуст.
TABLE = AdminPanelNotificationState.__tablename__


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


def test_migration_creates_state_table_once(file_engine):
    with file_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE {TABLE}"))

    assert TABLE not in set(inspect(file_engine).get_table_names())

    database._migrate_admin_panel_notification_states()
    database._migrate_admin_panel_notification_states()  # повторный запуск не должен падать

    assert TABLE in set(inspect(file_engine).get_table_names())
    columns = {col["name"] for col in inspect(file_engine).get_columns(TABLE)}
    assert columns == {"id", "user_id", "notification_id", "read_at", "hidden_at", "snoozed_until"}
    indexes = {ix["name"] for ix in inspect(file_engine).get_indexes(TABLE)}
    assert {"ix_apns_user_hidden", "ix_apns_user_snooze"} <= indexes
