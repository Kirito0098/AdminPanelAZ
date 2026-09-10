from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import run_db_migrations
from app.models import AmneziaWg2AccessPolicy, OpenVpnAccessPolicy, UnlockCode, UnlockCodeRedemption, WgAccessPolicy


def _create_legacy_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER NOT NULL PRIMARY KEY,
                    username VARCHAR(64),
                    role VARCHAR(16) NOT NULL,
                    telegram_id VARCHAR(32),
                    can_create_configs INTEGER
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE openvpn_access_policy (
                    id INTEGER NOT NULL PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    client_name VARCHAR(64) NOT NULL,
                    is_temp_blocked BOOLEAN,
                    is_permanent_blocked BOOLEAN,
                    block_reason VARCHAR(32),
                    block_started_at DATETIME,
                    block_days INTEGER,
                    block_until DATETIME,
                    traffic_limit_bytes BIGINT,
                    traffic_limit_period_days INTEGER,
                    updated_by VARCHAR(64),
                    updated_at DATETIME,
                    UNIQUE (node_id, client_name),
                    FOREIGN KEY(node_id) REFERENCES nodes (id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE amneziawg2_access_policies (
                    id INTEGER NOT NULL PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    client_name VARCHAR(64) NOT NULL,
                    is_temp_blocked BOOLEAN,
                    is_permanent_blocked BOOLEAN,
                    block_reason VARCHAR(32),
                    block_started_at DATETIME,
                    block_days INTEGER,
                    block_until DATETIME,
                    traffic_limit_bytes BIGINT,
                    traffic_limit_period_days INTEGER,
                    updated_by VARCHAR(64),
                    updated_at DATETIME,
                    UNIQUE (node_id, client_name),
                    FOREIGN KEY(node_id) REFERENCES nodes (id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE wg_access_policy (
                    id INTEGER NOT NULL PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    client_name VARCHAR(64) NOT NULL,
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
                    updated_at DATETIME,
                    UNIQUE (node_id, client_name),
                    FOREIGN KEY(node_id) REFERENCES nodes (id)
                )
                """
            )
        )


def test_unlock_code_models_and_migrations_smoke(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    _create_legacy_schema(engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))

    run_db_migrations()

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert UnlockCode.__tablename__ == "unlock_codes"
    assert UnlockCodeRedemption.__tablename__ == "unlock_code_redemptions"
    assert {"unlock_codes", "unlock_code_redemptions"}.issubset(tables)
    assert "access_until" in {col["name"] for col in inspector.get_columns("openvpn_access_policy")}
    assert "access_until" in {col["name"] for col in inspector.get_columns("amneziawg2_access_policies")}
    assert "access_until" not in {col["name"] for col in inspector.get_columns("wg_access_policy")}

    engine.dispose()


def test_unlock_code_model_metadata():
    assert OpenVpnAccessPolicy.__tablename__ == "openvpn_access_policy"
    assert AmneziaWg2AccessPolicy.__tablename__ == "amneziawg2_access_policies"
    assert WgAccessPolicy.__tablename__ == "wg_access_policy"
