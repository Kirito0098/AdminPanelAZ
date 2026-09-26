"""At-most-once processing of Telegram webhook updates (shared across uvicorn workers)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.models import TelegramProcessedUpdate

# Telegram stops redelivering an unacknowledged update well within a day;
# old rows are purged by the periodic retention job, not per update.
PROCESSED_UPDATE_RETENTION = timedelta(days=2)


def claim_telegram_update(db: Session, update_id: object) -> bool:
    """Record ``update_id``; False when it was already claimed (a redelivery)."""
    if not isinstance(update_id, int) or isinstance(update_id, bool):
        return True
    db.add(TelegramProcessedUpdate(update_id=update_id, received_at=datetime.utcnow()))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


def carry_over_processed_updates(source_db: Path, target_db: Path) -> int:
    """Copy claimed update ids from ``source_db`` into ``target_db``; returns the number of source rows.

    A DB restored from a backup does not know updates claimed after the backup was taken,
    so a redelivered bot "restore" command would run again after the panel restarts.
    """
    table = TelegramProcessedUpdate.__table__
    with closing(sqlite3.connect(f"file:{source_db.resolve().as_posix()}?mode=ro", uri=True)) as source:
        exists = source.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table.name,)
        ).fetchone()
        if exists is None:
            return 0
        rows = source.execute(f"SELECT update_id, received_at FROM {table.name}").fetchall()
    if not rows:
        return 0
    engine = create_engine(f"sqlite:///{target_db}", poolclass=NullPool)
    try:
        table.create(engine, checkfirst=True)
        with engine.begin() as conn:
            conn.exec_driver_sql(
                f"INSERT OR IGNORE INTO {table.name} (update_id, received_at) VALUES (?, ?)", rows
            )
    finally:
        engine.dispose()
    return len(rows)
