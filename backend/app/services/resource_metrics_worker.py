"""Background worker — polls node metrics and stores resource history."""

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node
from app.services.node_manager import _is_vpn_node, get_adapter_for_node
from app.services.admin_notify import admin_notify_service
from app.services.resource_metrics import persist_sample, purge_old_samples

logger = logging.getLogger(__name__)


def _is_resource_monitor_enabled() -> bool:
    """Runtime gate — MONITOR_ENABLED / resource_monitor can flip without restart."""
    from app.services.feature_guards import get_feature_service

    return get_feature_service().is_enabled("resource_monitor")


async def run_resource_metrics_loop():
    settings = get_settings()
    if not settings.resource_metrics_enabled:
        return

    while True:
        settings = get_settings()
        interval = max(5, int(settings.resource_metrics_interval_seconds or 60))
        try:
            if not _is_resource_monitor_enabled():
                logger.debug("resource_metrics skipped — resource_monitor disabled")
            else:
                await asyncio.to_thread(_collect_all_nodes)
        except Exception as exc:
            logger.warning("Resource metrics collector error: %s", exc)
        await asyncio.sleep(interval)


def _collect_all_nodes():
    db = SessionLocal()
    try:
        nodes = db.query(Node).all()
        for node in nodes:
            if not _is_vpn_node(node):
                continue
            try:
                adapter = get_adapter_for_node(node)
                metrics = adapter.get_server_metrics()
                persist_sample(db, node.id, metrics)
                admin_notify_service.maybe_send_resource_alert(
                    db,
                    cpu_percent=float(metrics.get("cpu_percent") or 0),
                    ram_percent=float(metrics.get("memory_percent") or 0),
                    node_id=node.id,
                    node_name=node.name,
                )
            except Exception as exc:
                logger.debug("Resource metrics collect failed for node %s: %s", node.name, exc)
        # Retention worker purges node_resource_sample when enabled.
        if not get_settings().retention_enabled:
            purge_old_samples(db)
    finally:
        db.close()
