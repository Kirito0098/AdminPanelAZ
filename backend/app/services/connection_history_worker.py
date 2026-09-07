"""Background worker — samples VPN connection counts for NOC charts."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.services.connection_history import collect_connection_samples, purge_old_connection_samples

logger = logging.getLogger(__name__)


def _is_resource_monitor_enabled() -> bool:
    """Runtime gate — MONITOR_ENABLED / resource_monitor can flip without restart."""
    from app.services.feature_guards import get_feature_service

    return get_feature_service().is_enabled("resource_monitor")


async def run_connection_history_loop():
    settings = get_settings()
    if not settings.resource_metrics_enabled:
        return

    while True:
        settings = get_settings()
        interval = max(5, int(settings.resource_metrics_interval_seconds or 60))
        try:
            if not _is_resource_monitor_enabled():
                logger.debug("connection_history skipped — resource_monitor disabled")
            else:
                await asyncio.to_thread(_collect_once)
        except Exception as exc:
            logger.warning("Connection history collector error: %s", exc)
        await asyncio.sleep(interval)


def _collect_once():
    db = SessionLocal()
    try:
        collect_connection_samples(db)
        # Retention worker already purges connection_count_samples in batches.
        # Only purge here when retention is off so samples still age out.
        if not get_settings().retention_enabled:
            purge_old_connection_samples(db)
    finally:
        db.close()
