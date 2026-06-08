"""Database migration tests (AZ run_db_migrations parity with AA db_migration_service)."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, run_db_migrations


def test_run_db_migrations_adds_traffic_limit_columns(tmp_path, monkeypatch):
    db_path = tmp_path / "migrate_traffic.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr("app.database.engine", engine)
    monkeypatch.setattr("app.database.SessionLocal", sessionmaker(bind=engine))

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE wg_access_policy (
                    id INTEGER PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    client_name VARCHAR(255) NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE openvpn_access_policy (
                    id INTEGER PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    client_name VARCHAR(255) NOT NULL
                )
                """
            )
        )

    run_db_migrations()

    insp = inspect(engine)
    wg_cols = {col["name"] for col in insp.get_columns("wg_access_policy")}
    ovpn_cols = {col["name"] for col in insp.get_columns("openvpn_access_policy")}
    assert "traffic_limit_bytes" in wg_cols
    assert "traffic_limit_period_days" in wg_cols
    assert "traffic_limit_bytes" in ovpn_cols
    assert "traffic_limit_period_days" in ovpn_cols


def test_run_db_migrations_creates_panel_resource_sample(tmp_path, monkeypatch):
    db_path = tmp_path / "migrate_panel_metrics.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr("app.database.engine", engine)
    monkeypatch.setattr("app.database.SessionLocal", sessionmaker(bind=engine))

    run_db_migrations()

    assert "panel_resource_sample" in inspect(engine).get_table_names()


def test_run_db_migrations_backfills_telegram_id(tmp_path, monkeypatch):
    db_path = tmp_path / "migrate_tg.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr("app.database.engine", engine)
    monkeypatch.setattr("app.database.SessionLocal", sessionmaker(bind=engine))

    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()
    try:
        from app.models import User, UserRole

        session.add(
            User(
                username="tg_123456789",
                password_hash="hash",
                role=UserRole.admin,
                is_active=True,
                telegram_id=None,
            )
        )
        session.commit()
        user_id = session.query(User).filter(User.username == "tg_123456789").one().id
    finally:
        session.close()

    run_db_migrations()

    with engine.connect() as conn:
        row = conn.execute(text("SELECT telegram_id FROM users WHERE id = :id"), {"id": user_id}).first()
    assert row[0] == "123456789"


def test_run_db_migrations_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "migrate_idempotent.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr("app.database.engine", engine)
    monkeypatch.setattr("app.database.SessionLocal", sessionmaker(bind=engine))

    run_db_migrations()
    first_tables = set(inspect(engine).get_table_names())
    run_db_migrations()
    assert set(inspect(engine).get_table_names()) == first_tables
