import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def run_db_migrations() -> None:
    """Lightweight SQLite migrations for columns added after initial deploy."""
    inspector = inspect(engine)
    migrations = {
        "wg_access_policy": [
            ("traffic_limit_bytes", "BIGINT"),
            ("traffic_limit_period_days", "INTEGER"),
        ],
        "openvpn_access_policy": [
            ("traffic_limit_bytes", "BIGINT"),
            ("traffic_limit_period_days", "INTEGER"),
        ],
        "users": [
            ("totp_secret_encrypted", "VARCHAR(512)"),
            ("totp_enabled", "INTEGER DEFAULT 0"),
            ("totp_backup_codes_encrypted", "VARCHAR(1024)"),
        ],
    }
    with engine.begin() as conn:
        for table, columns in migrations.items():
            if table not in inspector.get_table_names():
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, col_type in columns:
                if name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
                logger.info("DB migration: added %s.%s", table, name)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
