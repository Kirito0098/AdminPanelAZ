"""Запуск панели на БД, созданной 2.25.1: миграции проходят, схема совпадает с моделями, данные на месте."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app import database
from app.database import Base
from app.models import Node, UnlockCodeRedemption, User

SCHEMA_2_25_1 = Path(__file__).parent / "fixtures" / "schema_2_25_1.sql"


@pytest.fixture()
def db_2_25_1(tmp_path: Path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'adminpanel.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        database.apply_sqlite_connection_pragmas(dbapi_connection.cursor())

    raw = engine.raw_connection()
    try:
        raw.executescript(SCHEMA_2_25_1.read_text(encoding="utf-8"))
        raw.executescript(
            """
            INSERT INTO users (id, username, password_hash, role, theme, timezone, last_client_timezone,
                               noc_daily_time, noc_weekly_dow, noc_weekly_time, is_active,
                               must_change_password, totp_enabled, can_create_configs, created_at)
            VALUES (1, 'admin', 'x', 'admin', 'dark', '', '', '', '', '', 1, 0, 0, 1,
                    '2026-09-01 00:00:00');
            INSERT INTO nodes (id, name, host, port, api_key_hash, api_key_encrypted, status, is_local,
                               mtls_enabled, transport, ssh_port, ssh_private_key_encrypted,
                               ssh_passphrase_encrypted, ssh_remote_agent_host, ssh_host_key, node_kind,
                               node_metadata, wireguard_use_first_remote, openvpn_multihome,
                               created_at, updated_at)
            VALUES (1, 'local', '127.0.0.1', 8081, '', '', 'online', 1, 0, 'http', 22, '', '',
                    '127.0.0.1', '', 'vpn', '{}', 0, 0, '2026-09-01 00:00:00', '2026-09-01 00:00:00'),
                   (2, 'remote', '10.0.0.2', 8081, '', '', 'online', 0, 0, 'http', 22, '', '',
                    '127.0.0.1', '', 'vpn', '{}', 0, 0, '2026-09-01 00:00:00', '2026-09-01 00:00:00');
            INSERT INTO unlock_codes (id, code, grant_days, protocols, mode, max_redemptions,
                                      redemption_count, allowed_client_names, created_at)
            VALUES (1, 'PROMO2025', 30, '["openvpn"]', 'multi', 10, 2, '[]', '2026-09-01 00:00:00');
            INSERT INTO unlock_code_redemptions (id, code_id, client_name, node_id, redeemed_at)
            VALUES (1, 1, 'alice', 1, '2026-09-02 00:00:00'),
                   (2, 1, 'bob', 2, '2026-09-03 00:00:00');
            """
        )
        raw.commit()
    finally:
        raw.close()

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    yield engine
    engine.dispose()


def _upgrade() -> None:
    # Порядок как в main._seed_database.
    Base.metadata.create_all(bind=database.engine)
    database.run_db_migrations()


def test_migrations_pass_and_schema_matches_models(db_2_25_1):
    _upgrade()

    inspector = inspect(db_2_25_1)
    missing = {
        table.name: sorted(
            column.name
            for column in table.columns
            if column.name not in {c["name"] for c in inspector.get_columns(table.name)}
        )
        for table in Base.metadata.sorted_tables
    }
    assert {name: cols for name, cols in missing.items() if cols} == {}


def test_upgrade_keeps_data(db_2_25_1):
    _upgrade()

    db = database.SessionLocal()
    try:
        assert [n.name for n in db.query(Node).order_by(Node.id)] == ["local", "remote"]
        assert db.query(User).one().username == "admin"
        redemptions = db.query(UnlockCodeRedemption).order_by(UnlockCodeRedemption.id).all()
        assert [(r.client_name, r.node_id, r.user_id) for r in redemptions] == [
            ("alice", 1, None),
            ("bob", 2, None),
        ]
    finally:
        db.close()


def test_second_start_is_noop(db_2_25_1):
    _upgrade()
    with db_2_25_1.connect() as conn:
        before = conn.execute(text("SELECT type, name, sql FROM sqlite_master ORDER BY name")).all()
    _upgrade()
    with db_2_25_1.connect() as conn:
        after = conn.execute(text("SELECT type, name, sql FROM sqlite_master ORDER BY name")).all()
    assert after == before
