from __future__ import annotations

import fcntl
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base
from app.models import Node, OpenVpnAccessPolicy

_LEGACY_OVPN_POLICY = """
    CREATE TABLE openvpn_access_policy (
        id INTEGER NOT NULL PRIMARY KEY,
        client_name VARCHAR(64),
        is_temp_blocked BOOLEAN,
        is_permanent_blocked BOOLEAN,
        block_reason VARCHAR(32),
        block_started_at DATETIME,
        block_days INTEGER,
        block_until DATETIME,
        traffic_limit_bytes BIGINT,
        traffic_limit_period_days INTEGER,
        updated_by VARCHAR(64),
        updated_at DATETIME
    )
"""

_LEGACY_WG_POLICY = """
    CREATE TABLE wg_access_policy (
        id INTEGER NOT NULL PRIMARY KEY,
        client_name VARCHAR(64),
        expires_at DATETIME,
        is_temp_blocked BOOLEAN,
        is_permanent_blocked BOOLEAN,
        block_reason VARCHAR(32),
        block_started_at DATETIME,
        block_days INTEGER,
        block_until DATETIME,
        traffic_limit_bytes BIGINT,
        traffic_limit_period_days INTEGER,
        updated_by VARCHAR(64),
        updated_at DATETIME
    )
"""


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
    session = sessionmaker(bind=engine)()
    session.add(Node(id=1, name="local", host="127.0.0.1", is_local=True))
    session.add(Node(id=2, name="remote", host="10.0.0.2", is_local=False))
    session.commit()
    session.close()
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    yield engine
    engine.dispose()


def _replace_table(engine, table: str, ddl: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE {table}"))
    with engine.begin() as conn:
        conn.execute(text(ddl))


def _tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _columns(engine, table: str) -> set[str]:
    return {col["name"] for col in inspect(engine).get_columns(table)}


def test_failed_table_rebuild_leaves_no_half_migrated_schema(file_engine):
    _replace_table(file_engine, "openvpn_access_policy", _LEGACY_OVPN_POLICY)
    with file_engine.begin() as conn:
        conn.execute(text("INSERT INTO openvpn_access_policy (id, client_name) VALUES (1, NULL)"))

    with pytest.raises(IntegrityError):
        database._migrate_access_policy_node_scope()

    assert "openvpn_access_policy_new" not in _tables(file_engine)
    assert "node_id" not in _columns(file_engine, "openvpn_access_policy")

    with file_engine.begin() as conn:
        conn.execute(text("UPDATE openvpn_access_policy SET client_name = 'alice' WHERE id = 1"))
    database._migrate_access_policy_node_scope()

    assert "node_id" in _columns(file_engine, "openvpn_access_policy")
    with file_engine.connect() as conn:
        assert conn.execute(text("SELECT client_name FROM openvpn_access_policy")).scalars().all() == ["alice"]


def test_table_rebuild_ignores_leftover_from_older_crash(file_engine):
    _replace_table(file_engine, "openvpn_access_policy", _LEGACY_OVPN_POLICY)
    with file_engine.begin() as conn:
        conn.execute(text("INSERT INTO openvpn_access_policy (id, client_name) VALUES (1, 'alice')"))
        conn.execute(text("CREATE TABLE openvpn_access_policy_new (id INTEGER PRIMARY KEY)"))

    database._migrate_access_policy_node_scope()

    assert "openvpn_access_policy_new" not in _tables(file_engine)
    assert "node_id" in _columns(file_engine, "openvpn_access_policy")


def test_policy_rebuild_resumes_when_only_first_table_was_migrated(file_engine):
    session = database.SessionLocal()
    session.add(OpenVpnAccessPolicy(node_id=2, client_name="alice"))
    session.commit()
    session.close()
    _replace_table(file_engine, "wg_access_policy", _LEGACY_WG_POLICY)
    with file_engine.begin() as conn:
        conn.execute(text("INSERT INTO wg_access_policy (id, client_name) VALUES (1, 'bob')"))

    database._migrate_access_policy_node_scope()

    assert "node_id" in _columns(file_engine, "wg_access_policy")
    with file_engine.connect() as conn:
        assert conn.execute(text("SELECT client_name, node_id FROM wg_access_policy")).all() == [("bob", 1)]
        assert conn.execute(text("SELECT client_name, node_id FROM openvpn_access_policy")).all() == [("alice", 2)]


def test_migration_transaction_rolls_back_ddl(file_engine):
    with pytest.raises(RuntimeError):
        with database._migration_transaction() as conn:
            conn.execute(text("CREATE TABLE scratch (x INTEGER)"))
            raise RuntimeError("crash")
    assert "scratch" not in _tables(file_engine)

    with database._migration_transaction() as conn:
        conn.execute(text("CREATE TABLE scratch (x INTEGER)"))
    assert "scratch" in _tables(file_engine)


def test_run_db_migrations_holds_exclusive_lock(file_engine, tmp_path: Path, monkeypatch):
    lock_path = tmp_path / "adminpanel.db.migrate.lock"
    observed: list[bool] = []

    def probe() -> None:
        with lock_path.open("a") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                observed.append(True)
            else:
                fcntl.flock(fh, fcntl.LOCK_UN)
                observed.append(False)

    monkeypatch.setattr(database, "_migrate_alert_rules_table", probe)
    monkeypatch.setattr(database, "_seed_client_templates_for_nodes", lambda: None)

    database.run_db_migrations()

    assert observed == [True]
    assert (lock_path.stat().st_mode & 0o777) == 0o600
