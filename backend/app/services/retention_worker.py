"""Background retention purge loop."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.services.retention import run_retention_purge

logger = logging.getLogger(__name__)


async def run_retention_loop() -> None:
    """Purge loop — re-checks RETENTION_ENABLED each tick (settings API can flip it)."""
    while True:
        settings = get_settings()
        interval = max(3600, int(settings.retention_interval_hours or 24) * 3600)
        try:
            if not settings.retention_enabled:
                logger.debug("retention skipped — RETENTION_ENABLED disabled")
            else:
                await asyncio.to_thread(_purge_once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Retention purge error: %s", exc)
        await asyncio.sleep(interval)


def _purge_once() -> None:
    db = SessionLocal()
    try:
        counts = run_retention_purge(db)
        if counts.get("total", 0) > 0:
            logger.info("Retention purge removed rows: %s", counts)
    finally:
        db.close()
