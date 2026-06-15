"""Background worker for self-service user reminders."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.services.user_reminder_service import process_user_reminders

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_user_reminder_loop() -> None:
    interval = max(300, int(settings.self_service_reminder_interval_seconds))
    while True:
        await asyncio.sleep(interval)
        db = SessionLocal()
        try:
            count = process_user_reminders(db)
            if count:
                logger.info("user_reminder: sent %s notifications", count)
        except Exception:
            logger.exception("user_reminder failed")
        finally:
            db.close()
