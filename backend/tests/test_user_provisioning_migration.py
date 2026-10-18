"""Stage 1: users provisioning columns + user_node_assignments (legacy → migrate)."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.database import _migrate_users_provisioning

_LEGACY_USERS = """
CREATE TABLE users (
    id INTEGER NOT NULL PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(16) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    must_change_password BOOLEAN NOT NULL DEFAULT 0,
    token_version INTEGER NOT NULL DEFAULT 0,
    totp_enabled BOOLEAN NOT NULL DEFAULT 0,
    can_create_configs BOOLEAN NOT NULL DEFAULT 1,
    can_manage_configs BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL
)
"""

_LEGACY_BACKGROUND_TASK = """
CREATE TABLE background_task (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    task_type VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    created_by_username VARCHAR(80),
    message VARCHAR(255),
    output TEXT,
    error TEXT,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    progress_stage VARCHAR(255),
    created_at DATETIME,
    started_at DATETIME,
    finished_at DATETIME,
    owner VARCHAR(64)
)
"""

_LEGACY_NODES = """
CREATE TABLE nodes (
    id INTEGER NOT NULL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    host VARCHAR(255) NOT NULL
)
"""


def test_migrate_users_provisioning_adds_columns_only(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text(_LEGACY_USERS))
        conn.execute(text(_LEGACY_BACKGROUND_TASK))
        conn.execute(text(_LEGACY_NODES))
        conn.execute(
            text(
                "INSERT INTO users (username, password_hash, role, is_active, must_change_password, "
                "token_version, totp_enabled, can_create_configs, can_manage_configs, created_at) "
                "VALUES ('old', 'x', 'user', 1, 0, 0, 0, 1, 0, CURRENT_TIMESTAMP)"
            )
        )

    monkeypatch.setattr(database, "engine", engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    _migrate_users_provisioning()

    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "client_base_name" in cols
    assert "plan_config_indexes" in cols
    assert "desired_protocols" in cols
    assert "panel_login_enabled" in cols
    assert "provision_state" in cols
    assert "user_node_assignments" in inspect(engine).get_table_names()
    bt_cols = {c["name"] for c in inspect(engine).get_columns("background_task")}
    assert "subject_key" in bt_cols

    row = db.execute(
        text(
            "SELECT client_base_name, plan_config_indexes, desired_protocols, "
            "panel_login_enabled, provision_state FROM users WHERE username='old'"
        )
    ).one()
    assert row[0] is None and row[1] is None and row[2] is None
    assert row[3] in (1, True) and row[4] == "unmanaged"
    assert db.execute(text("SELECT COUNT(*) FROM user_node_assignments")).scalar() == 0

    # Idempotent: second call must not error.
    _migrate_users_provisioning()
    assert "client_base_name" in {c["name"] for c in inspect(engine).get_columns("users")}

    db.close()
    engine.dispose()
