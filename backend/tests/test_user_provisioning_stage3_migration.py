"""Stage 3 migration: suspend / traffic-limit / unlock-code comment columns."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import _migrate_users_stage3


def _build_pre_stage3_schema(engine) -> None:
    """Minimal schema as before Stage 3 columns existed (upgrade path)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER NOT NULL PRIMARY KEY,
                    username VARCHAR(80) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(16) NOT NULL,
                    theme VARCHAR(16),
                    timezone VARCHAR(64),
                    last_client_timezone VARCHAR(64),
                    noc_daily_time VARCHAR(8),
                    noc_weekly_dow VARCHAR(8),
                    noc_weekly_time VARCHAR(8),
                    is_active BOOLEAN,
                    must_change_password BOOLEAN,
                    token_version INTEGER,
                    totp_enabled BOOLEAN,
                    can_create_configs BOOLEAN,
                    can_manage_configs BOOLEAN,
                    panel_login_enabled BOOLEAN DEFAULT 1,
                    provision_state VARCHAR(16) DEFAULT 'unmanaged',
                    created_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE unlock_codes (
                    id INTEGER NOT NULL PRIMARY KEY,
                    code VARCHAR(32) NOT NULL UNIQUE,
                    grant_days INTEGER NOT NULL,
                    protocols TEXT NOT NULL DEFAULT '[]',
                    mode VARCHAR(8) NOT NULL,
                    max_redemptions INTEGER NOT NULL,
                    redemption_count INTEGER NOT NULL DEFAULT 0,
                    allowed_client_names TEXT NOT NULL DEFAULT '[]',
                    code_expires_at DATETIME,
                    created_by_user_id INTEGER,
                    created_at DATETIME,
                    revoked_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE background_task (
                    id INTEGER NOT NULL PRIMARY KEY,
                    task_type VARCHAR(64) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    subject_key VARCHAR(64)
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (username, password_hash, role, is_active, must_change_password, "
                "token_version, totp_enabled, can_create_configs, can_manage_configs, "
                "panel_login_enabled, provision_state, created_at) "
                "VALUES ('old', 'x', 'user', 1, 0, 0, 0, 1, 0, 1, 'unmanaged', CURRENT_TIMESTAMP)"
            )
        )


def test_migrate_stage3_adds_columns_from_pre_stage3_schema(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    _build_pre_stage3_schema(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    before = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "suspended_at" not in before
    assert "traffic_limit_bytes" not in before

    monkeypatch.setattr("app.database.engine", engine)
    _migrate_users_stage3()
    _migrate_users_stage3()  # idempotent

    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "suspended_at" in cols
    assert "traffic_limit_bytes" in cols
    assert "traffic_counter_reset_at" in cols
    assert "traffic_limit_blocked" in cols
    assert "suspend_reason" in cols
    assert "suspend_reason_visible" in cols

    uc = {c["name"] for c in inspect(engine).get_columns("unlock_codes")}
    assert "comment" in uc

    bt = {c["name"] for c in inspect(engine).get_columns("background_task")}
    assert "input" in bt

    row = db.execute(
        text(
            "SELECT suspended_at, traffic_limit_bytes, traffic_limit_blocked "
            "FROM users WHERE username='old'"
        )
    ).one()
    assert row[0] is None and row[1] is None and row[2] in (0, False)
    db.close()
