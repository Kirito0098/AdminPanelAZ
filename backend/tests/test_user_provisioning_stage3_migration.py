"""Stage 3 migration: suspend / traffic-limit / unlock-code comment columns."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  register all declarative tables with Base.metadata
from app.database import Base, _migrate_users_stage3


def test_migrate_stage3_adds_columns_only(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.execute(text(
        "INSERT INTO users (username, password_hash, role, theme, timezone, last_client_timezone, "
        "noc_daily_time, noc_weekly_dow, noc_weekly_time, is_active, must_change_password, "
        "token_version, totp_enabled, can_create_configs, can_manage_configs, panel_login_enabled, "
        "provision_state, suspend_reason_visible, traffic_limit_blocked, created_at) "
        "VALUES ('old', 'x', 'user', 'dark', '', '', '', '', '', 1, 0, 0, 0, 1, 0, 1, 'unmanaged', 0, 0, CURRENT_TIMESTAMP)"
    ))
    db.commit()
    monkeypatch.setattr("app.database.engine", engine)
    _migrate_users_stage3()
    _migrate_users_stage3()  # idempotent
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "suspended_at" in cols
    assert "traffic_limit_bytes" in cols
    assert "traffic_counter_reset_at" in cols
    assert "traffic_limit_blocked" in cols
    uc = {c["name"] for c in inspect(engine).get_columns("unlock_codes")}
    assert "comment" in uc
    row = db.execute(text(
        "SELECT suspended_at, traffic_limit_bytes, traffic_limit_blocked FROM users WHERE username='old'"
    )).one()
    assert row[0] is None and row[1] is None and row[2] in (0, False)
