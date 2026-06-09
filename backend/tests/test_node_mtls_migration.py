"""Per-node mtls_enabled column migration and backfill tests."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base, run_db_migrations


def _setup_engine(tmp_path, monkeypatch, db_name: str):
    db_path = tmp_path / db_name
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr("app.database.engine", engine)
    monkeypatch.setattr("app.database.SessionLocal", sessionmaker(bind=engine))
    return engine


def _create_legacy_nodes_table(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE nodes (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    host VARCHAR(255) NOT NULL,
                    port INTEGER DEFAULT 9100,
                    api_key_hash VARCHAR(255) DEFAULT '',
                    api_key_encrypted VARCHAR(512) DEFAULT '',
                    status VARCHAR(32) DEFAULT 'unknown',
                    last_seen_at DATETIME,
                    is_local INTEGER DEFAULT 0,
                    node_metadata TEXT DEFAULT '{}',
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO nodes (name, host, port, is_local)
                VALUES ('local', '127.0.0.1', 9100, 1),
                       ('remote-a', '10.0.0.1', 9100, 0),
                       ('remote-b', '10.0.0.2', 9100, 0)
                """
            )
        )


def test_run_db_migrations_adds_mtls_enabled_column(tmp_path, monkeypatch):
    engine = _setup_engine(tmp_path, monkeypatch, "migrate_mtls_col.db")
    _create_legacy_nodes_table(engine)
    monkeypatch.setattr(
        "app.database.get_settings",
        lambda: Settings(node_agent_mtls_enabled=False),
    )

    run_db_migrations()

    cols = {col["name"] for col in inspect(engine).get_columns("nodes")}
    assert "mtls_enabled" in cols

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name, mtls_enabled FROM nodes ORDER BY name")
        ).mappings().all()
    assert [dict(r) for r in rows] == [
        {"name": "local", "mtls_enabled": 0},
        {"name": "remote-a", "mtls_enabled": 0},
        {"name": "remote-b", "mtls_enabled": 0},
    ]


def test_run_db_migrations_mtls_backfill_when_global_flag_enabled(tmp_path, monkeypatch):
    engine = _setup_engine(tmp_path, monkeypatch, "migrate_mtls_backfill.db")
    _create_legacy_nodes_table(engine)
    monkeypatch.setattr(
        "app.database.get_settings",
        lambda: Settings(node_agent_mtls_enabled=True),
    )

    run_db_migrations()

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name, is_local, mtls_enabled FROM nodes ORDER BY name")
        ).mappings().all()
    assert [dict(r) for r in rows] == [
        {"name": "local", "is_local": 1, "mtls_enabled": 0},
        {"name": "remote-a", "is_local": 0, "mtls_enabled": 1},
        {"name": "remote-b", "is_local": 0, "mtls_enabled": 1},
    ]


def test_run_db_migrations_mtls_is_idempotent(tmp_path, monkeypatch):
    engine = _setup_engine(tmp_path, monkeypatch, "migrate_mtls_idempotent.db")
    _create_legacy_nodes_table(engine)
    monkeypatch.setattr(
        "app.database.get_settings",
        lambda: Settings(node_agent_mtls_enabled=True),
    )

    run_db_migrations()
    run_db_migrations()

    cols = {col["name"] for col in inspect(engine).get_columns("nodes")}
    assert "mtls_enabled" in cols

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name, mtls_enabled FROM nodes ORDER BY name")
        ).mappings().all()
    assert [dict(r) for r in rows] == [
        {"name": "local", "mtls_enabled": 0},
        {"name": "remote-a", "mtls_enabled": 1},
        {"name": "remote-b", "mtls_enabled": 1},
    ]


def test_run_db_migrations_mtls_on_fresh_schema(tmp_path, monkeypatch):
    engine = _setup_engine(tmp_path, monkeypatch, "migrate_mtls_fresh.db")
    import app.models  # noqa: F401 — register all ORM tables with Base.metadata

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(
        "app.database.get_settings",
        lambda: Settings(node_agent_mtls_enabled=False),
    )

    run_db_migrations()

    assert "mtls_enabled" in {col["name"] for col in inspect(engine).get_columns("nodes")}


def test_to_response_local_node_always_mtls_disabled():
    from datetime import datetime

    from app.models import Node, NodeStatus
    from app.routers.nodes import _to_response

    node = Node(
        id=1,
        name="local",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        mtls_enabled=True,
        status=NodeStatus.online,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    assert _to_response(node).mtls_enabled is False
