"""Background node health polling — keeps node status and metadata up to date."""

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node
from app.services.node_manager import check_node_health, update_node_from_health

logger = logging.getLogger(__name__)


def _is_node_health_sync_enabled() -> bool:
    """Runtime gate — NODE_HEALTH_SYNC_ENABLED can flip without relying on startup only."""
    return bool(get_settings().node_health_sync_enabled)


async def run_node_health_loop():
    """Health poll loop — re-checks NODE_HEALTH_SYNC_ENABLED each tick."""
    while True:
        settings = get_settings()
        interval = max(15, int(settings.node_health_sync_interval_seconds or 60))
        try:
            if not _is_node_health_sync_enabled():
                logger.debug("node_health skipped — NODE_HEALTH_SYNC_ENABLED disabled")
            else:
                await asyncio.to_thread(_poll_all_nodes)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Node health poll error: %s", exc)
        await asyncio.sleep(interval)


def _poll_all_nodes():
    db = SessionLocal()
    try:
        nodes = db.query(Node).all()
        for node in nodes:
            try:
                health = check_node_health(node)
                update_node_from_health(node, health, db)
            except Exception as exc:
                logger.debug("Node health poll failed for %s: %s", node.name, exc)
    finally:
        db.close()
