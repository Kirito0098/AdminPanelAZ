from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import database
from app.services.feature_toggles import FeatureToggleService, is_node_ssh_transport_enabled


def test_node_ssh_transport_defaults_off(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    service = FeatureToggleService(env_file)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", lambda: service)

    assert service.is_enabled("node_ssh_transport") is False
    assert is_node_ssh_transport_enabled(None) is False


def test_nodes_ssh_migration_adds_expected_columns(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE nodes (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    host VARCHAR(255) NOT NULL,
                    port INTEGER NOT NULL DEFAULT 9100,
                    api_key_hash VARCHAR(255) NOT NULL DEFAULT '',
                    api_key_encrypted VARCHAR(512) NOT NULL DEFAULT '',
                    status VARCHAR(20) NOT NULL DEFAULT 'unknown',
                    last_seen_at DATETIME,
                    is_local INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        )

    old_engine = database.engine
    old_session_local = database.SessionLocal
    try:
        database.engine = engine
        database.SessionLocal = sessionmaker(bind=engine)
        monkeypatch.setattr(database, "_seed_client_templates_for_nodes", lambda: None)
        database.run_db_migrations()
        columns = {col["name"] for col in inspect(engine).get_columns("nodes")}
    finally:
        database.engine = old_engine
        database.SessionLocal = old_session_local
        engine.dispose()

    assert {
        "ssh_host",
        "ssh_port",
        "ssh_username",
        "ssh_private_key_encrypted",
        "ssh_passphrase_encrypted",
        "ssh_remote_agent_host",
        "ssh_remote_agent_port",
    }.issubset(columns)
