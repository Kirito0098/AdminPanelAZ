"""Background worker — collects panel process metrics on the controller."""

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.services.admin_notify import admin_notify_service
from app.services.panel_resource_metrics import persist_sample, purge_old_samples
from app.services.resource_alert_sustained import SustainedMetricSource

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
        from app.services.panel_resource_collector import collect_panel_metrics

        metrics = collect_panel_metrics()
        persist_sample(db, metrics)
        purge_old_samples(db)
        admin_notify_service.maybe_send_resource_alert(
            db,
            cpu_percent=float(metrics.get("backend_cpu_percent") or 0),
            ram_percent=None,
            node_name="Panel",
            cpu_source=SustainedMetricSource.panel_backend_cpu,
        )
    finally:
        db.close()
