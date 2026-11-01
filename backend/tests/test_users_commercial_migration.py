"""Migration: users.note + user_action_logs.target_user_id."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.database import _migrate_users_commercial

_LEGACY_USERS = "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64))"
_LEGACY_LOGS = (
    "CREATE TABLE user_action_logs ("
    "id INTEGER PRIMARY KEY, user_id INTEGER, username VARCHAR(64), "
    "action VARCHAR(64), details TEXT, remote_addr VARCHAR(64), created_at DATETIME)"
)


def _legacy_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.begin() as conn:
        conn.execute(text(_LEGACY_USERS))
        conn.execute(text(_LEGACY_LOGS))
    return engine


def test_migrate_users_commercial_adds_columns(monkeypatch):
    engine = _legacy_engine()
    monkeypatch.setattr("app.database.engine", engine)
    _migrate_users_commercial()
    assert "note" in {c["name"] for c in inspect(engine).get_columns("users")}
    assert "target_user_id" in {
        c["name"] for c in inspect(engine).get_columns("user_action_logs")
    }
    # Idempotent: second run must not raise.
    _migrate_users_commercial()

