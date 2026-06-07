"""Scheduled nightly CIDR DB refresh worker."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.database import SessionLocal
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService

logger = logging.getLogger(__name__)


def _seconds_until_next_run(hour: int, minute: int) -> float:
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_cidr_db_scheduler_loop() -> None:
    settings = get_settings()
    while True:
        try:
            if not settings.cidr_db_refresh_enabled:
                await asyncio.sleep(3600)
                continue
            delay = _seconds_until_next_run(settings.cidr_db_refresh_hour, settings.cidr_db_refresh_minute)
            logger.info("CIDR DB scheduler: next refresh in %.0f seconds", delay)
            await asyncio.sleep(delay)
            db = SessionLocal()
            try:
                svc = CidrDbUpdaterService(db=db)
                logger.info("CIDR DB scheduler: starting nightly refresh")
                result = svc.refresh_all_providers(triggered_by="cron")
                logger.info(
                    "CIDR DB scheduler: done status=%s updated=%d failed=%d",
                    result.get("status"),
                    result.get("providers_updated", 0),
                    result.get("providers_failed", 0),
                )
            finally:
                db.close()
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("CIDR DB scheduler error: %s", exc)
            await asyncio.sleep(300)
