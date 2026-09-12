"""Background worker — collects panel process metrics on the controller."""

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.services.admin_notify import admin_notify_service
from app.services.panel_resource_metrics import persist_sample, purge_old_samples
from app.services.resource_alert_sustained import SustainedMetricSource

logger = logging.getLogger(__name__)


def _is_resource_monitor_enabled() -> bool:
    """Runtime gate — MONITOR_ENABLED / resource_monitor can flip without restart."""
    from app.services.feature_guards import get_feature_service

    return get_feature_service().is_enabled("resource_monitor")


async def run_panel_resource_metrics_loop():
    while True:
        settings = get_settings()
        interval = max(5, int(settings.panel_resource_metrics_interval_seconds or 60))
        try:
            if not settings.panel_resource_metrics_enabled:
                logger.debug("panel_resource_metrics skipped — panel_resource_metrics_enabled disabled")
            elif not _is_resource_monitor_enabled():
                logger.debug("panel_resource_metrics skipped — resource_monitor disabled")
            else:
                await asyncio.to_thread(_collect_sample)
        except Exception as exc:
            logger.warning("Panel resource metrics collector error: %s", exc)
        await asyncio.sleep(interval)


def _collect_sample():
    db = SessionLocal()
    try:
        from app.services.panel_resource_collector import collect_panel_metrics

        metrics = collect_panel_metrics()
        persist_sample(db, metrics)
        # Retention worker purges panel_resource_sample when enabled.
        if not get_settings().retention_enabled:
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
