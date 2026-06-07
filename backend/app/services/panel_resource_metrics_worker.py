"""Background worker — collects panel process metrics on the controller."""

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.services.panel_resource_metrics import persist_sample, purge_old_samples

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_panel_resource_metrics_loop():
    if not settings.panel_resource_metrics_enabled:
        return

    while True:
        try:
            await asyncio.to_thread(_collect_sample)
        except Exception as exc:
            logger.warning("Panel resource metrics collector error: %s", exc)
        await asyncio.sleep(settings.panel_resource_metrics_interval_seconds)


def _collect_sample():
    db = SessionLocal()
    try:
        persist_sample(db)
        purge_old_samples(db)
    finally:
        db.close()
