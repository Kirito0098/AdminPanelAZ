"""Stage 2 Task 1: migration + ORM for notification/request tables."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register all tables on Base before create_all

from app.database import Base, _migrate_user_provisioning_stage2


def test_stage2_migration_adds_tables_and_last_read(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.execute(
        text(
            "INSERT INTO users (username, password_hash, role, is_active, must_change_password, "
            "token_version, totp_enabled, can_create_configs, can_manage_configs, theme, timezone, "
            "last_client_timezone, noc_daily_time, noc_weekly_dow, noc_weekly_time, "
            "panel_login_enabled, provision_state, created_at) "
            "VALUES ('old', 'x', 'user', 1, 0, 0, 0, 1, 0, 'dark', '', '', '', '', '', 1, "
            "'unmanaged', CURRENT_TIMESTAMP)"
        )
    )
    db.commit()
    monkeypatch.setattr("app.database.engine", engine)
    _migrate_user_provisioning_stage2()
    tables = set(inspect(engine).get_table_names())
    assert "admin_panel_notifications" in tables
    assert "provisioning_presets" in tables
    assert "user_access_requests" in tables
    assert "telegram_request_bans" in tables
    assert "telegram_user_archive" in tables
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "last_read_notification_id" in cols
    assert (
        db.execute(text("SELECT last_read_notification_id FROM users WHERE username='old'")).scalar()
        is None
    )
