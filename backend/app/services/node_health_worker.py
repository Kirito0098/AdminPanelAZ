"""Background node health polling — keeps node status and metadata up to date."""

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node
from app.services.node_manager import check_node_health, update_node_from_health

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_node_health_loop():
    if not settings.node_health_sync_enabled:
        return

    while True:
        try:
            await asyncio.to_thread(_poll_all_nodes)
        except Exception as exc:
            logger.warning("Node health poll error: %s", exc)
        await asyncio.sleep(settings.node_health_sync_interval_seconds)


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
