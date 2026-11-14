"""Migration: user_messages table + users.chat_mode_since."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.database import _migrate_user_message_cards, _migrate_user_messages


def _legacy_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64))"))
    return engine


def test_migrate_user_messages_creates_table(monkeypatch):
    engine = _legacy_engine()
    monkeypatch.setattr("app.database.engine", engine)

    _migrate_user_messages()
    _migrate_user_message_cards()

    assert "user_messages" in set(inspect(engine).get_table_names())
    assert "user_message_cards" in set(inspect(engine).get_table_names())
    columns = {c["name"] for c in inspect(engine).get_columns("user_messages")}
    assert {"user_id", "direction", "admin_id", "text", "telegram_message_id", "read_by_admin_at"} <= columns
    assert "chat_mode_since" in {c["name"] for c in inspect(engine).get_columns("users")}

    # Идемпотентность: повторный прогон не падает.
    _migrate_user_messages()
    _migrate_user_message_cards()
