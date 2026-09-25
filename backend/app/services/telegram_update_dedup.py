"""At-most-once processing of Telegram webhook updates (shared across uvicorn workers)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import TelegramProcessedUpdate

# Telegram stops redelivering an unacknowledged update well within a day.
PROCESSED_UPDATE_RETENTION = timedelta(days=2)


def claim_telegram_update(db: Session, update_id: object) -> bool:
    """Record ``update_id``; False when it was already claimed (a redelivery)."""
    if not isinstance(update_id, int) or isinstance(update_id, bool):
        return True
    now = datetime.utcnow()
    db.query(TelegramProcessedUpdate).filter(
        TelegramProcessedUpdate.received_at < now - PROCESSED_UPDATE_RETENTION
    ).delete(synchronize_session=False)
    db.add(TelegramProcessedUpdate(update_id=update_id, received_at=now))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True
