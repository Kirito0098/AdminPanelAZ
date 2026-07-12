"""Background worker — samples VPN connection counts for NOC charts."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.services.connection_history import collect_connection_samples, purge_old_connection_samples

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_connection_history_loop():
    if not settings.resource_metrics_enabled:
        return

    while True:
        try:
            await asyncio.to_thread(_collect_once)
        except Exception as exc:
            logger.warning("Connection history collector error: %s", exc)
        await asyncio.sleep(settings.resource_metrics_interval_seconds)


def _collect_once():
    db = SessionLocal()
    try:
        collect_connection_samples(db)
        purge_old_connection_samples(db)
    finally:
        db.close()
