"""Separate SQLite database for bulk provider CIDR rows."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings
from app.database import apply_sqlite_connection_pragmas
from app.paths import BACKEND_ROOT

logger = logging.getLogger(__name__)
settings = get_settings()
_is_sqlite = settings.cidr_database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}
cidr_engine = create_engine(settings.cidr_database_url, connect_args=_connect_args)


@event.listens_for(cidr_engine, "connect")
def _set_cidr_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    if not _is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    apply_sqlite_connection_pragmas(cursor)
    cursor.close()


CidrSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cidr_engine)


class CidrBase(DeclarativeBase):
    pass


def resolve_sqlite_db_path(db_url: str, *, default_relative: str) -> Path:
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", ""))
        if not db_path.is_absolute():
            db_path = BACKEND_ROOT / db_path
        return db_path.resolve()
    return (BACKEND_ROOT / default_relative).resolve()


def resolve_cidr_db_path() -> Path:
    return resolve_sqlite_db_path(
        get_settings().cidr_database_url,
        default_relative="data/cidr/cidr.db",
    )


def get_cidr_db():
    db = CidrSessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_cidr_data_dirs() -> None:
    """Ensure SQLite CIDR paths exist before first DB open."""
    if not _is_sqlite:
        return
    from app.paths import resolve_backend_path

    cfg = get_settings()
    resolve_cidr_db_path().parent.mkdir(parents=True, exist_ok=True)
    resolve_backend_path(cfg.cidr_list_dir).mkdir(parents=True, exist_ok=True)
    resolve_backend_path(cfg.cidr_db_staging_dir).mkdir(parents=True, exist_ok=True)


def run_cidr_db_migrations() -> None:
    """Create cidr.db schema and one-time copy provider_cidr from adminpanel.db."""
    from app.cidr_models import ProviderCidr  # noqa: F401
    from app.database import engine as main_engine

    ensure_cidr_data_dirs()
    CidrBase.metadata.create_all(bind=cidr_engine)

    main_inspector = inspect(main_engine)
    if "provider_cidr" not in main_inspector.get_table_names():
        return

    with main_engine.connect() as conn:
        main_count = int(conn.execute(text("SELECT COUNT(*) FROM provider_cidr")).scalar() or 0)

    cidr_inspector = inspect(cidr_engine)
    cidr_count = 0
    if "provider_cidr" in cidr_inspector.get_table_names():
        with cidr_engine.connect() as conn:
            cidr_count = int(conn.execute(text("SELECT COUNT(*) FROM provider_cidr")).scalar() or 0)

    if main_count == 0:
        with main_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS provider_cidr"))
        logger.info("CIDR DB migration: dropped empty provider_cidr from main DB")
        return

    if cidr_count > 0:
        logger.warning(
            "CIDR DB migration skipped: main has %d provider_cidr rows but cidr.db already has %d",
            main_count,
            cidr_count,
        )
        return

    from app.database import resolve_main_db_path

    main_path = resolve_main_db_path()
    cidr_path = resolve_cidr_db_path()
    cidr_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "CIDR DB migration: copying %d provider_cidr rows from %s to %s",
        main_count,
        main_path,
        cidr_path,
    )

    conn = sqlite3.connect(str(cidr_path), timeout=30)
    try:
        apply_sqlite_connection_pragmas(conn.cursor())
        conn.execute("ATTACH DATABASE ? AS maindb", (str(main_path),))
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO provider_cidr (id, provider_key, cidr, region_scope, country_codes, refreshed_at)
            SELECT id, provider_key, cidr, region_scope, country_codes,
                   COALESCE(refreshed_at, datetime('now'))
            FROM maindb.provider_cidr
            """
        )
        conn.commit()
        migrated = int(
            conn.execute("SELECT COUNT(*) FROM provider_cidr").fetchone()[0]
        )
    finally:
        conn.close()

    if migrated != main_count:
        raise RuntimeError(
            f"CIDR DB migration count mismatch: expected {main_count}, got {migrated}"
        )

    with main_engine.begin() as conn:
        conn.execute(text("DROP TABLE provider_cidr"))

    logger.info("CIDR DB migration: migrated %d rows and dropped provider_cidr from main DB", migrated)
