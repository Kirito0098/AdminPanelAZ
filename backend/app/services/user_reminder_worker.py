"""Background worker for self-service user reminders."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.services.user_reminder_service import process_user_reminders
from app.services.background_gate import run_background_step

logger = logging.getLogger(__name__)


def _is_user_reminder_enabled() -> bool:
    """Runtime gate — SELF_SERVICE_REMINDER_ENABLED can flip without restart."""
    return bool(get_settings().self_service_reminder_enabled)


def _process_user_reminders_once() -> None:
    db = SessionLocal()
    try:
        count = process_user_reminders(db)
        if count:
            logger.info("user_reminder: sent %s notifications", count)
    finally:
        db.close()


async def run_user_reminder_loop() -> None:
    """Reminder loop — re-checks SELF_SERVICE_REMINDER_ENABLED each tick."""
    while True:
        settings = get_settings()
        interval = max(300, int(settings.self_service_reminder_interval_seconds or 3600))
        await asyncio.sleep(interval)
        try:
            if not _is_user_reminder_enabled():
                logger.debug(
                    "user_reminder skipped — SELF_SERVICE_REMINDER_ENABLED disabled"
                )
                continue
            # Sends Telegram messages one by one.
            await run_background_step(_process_user_reminders_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("user_reminder failed")
