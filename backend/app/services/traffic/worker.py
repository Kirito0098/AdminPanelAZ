"""Background traffic collector task."""

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node
from app.services.node_manager import get_adapter_for_node
from app.services.traffic.collector import TrafficCollectorService, build_status_rows

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_traffic_collector_loop():
    if not settings.traffic_sync_enabled:
        return

    while True:
        try:
            await asyncio.to_thread(_collect_all_nodes)
        except Exception as exc:
            logger.warning("Traffic collector error: %s", exc)
        await asyncio.sleep(settings.traffic_sync_interval_seconds)


def _collect_all_nodes():
    db = SessionLocal()
    try:
        nodes = db.query(Node).all()
        for node in nodes:
            try:
                adapter = get_adapter_for_node(node)
                ovpn = adapter.parse_openvpn_status()
                wg = adapter.parse_wireguard_status()
                status_rows = build_status_rows(ovpn, wg)
                collector = TrafficCollectorService(db, node.id)
                collector.persist_snapshot(status_rows)
                if settings.traffic_limit_reconcile_after_sync:
                    from app.services.traffic_limit_reconcile import reconcile_traffic_limit_policies_safe

                    reconcile_traffic_limit_policies_safe(db, node_id=node.id)
            except Exception as exc:
                logger.debug("Traffic collect failed for node %s: %s", node.name, exc)
    finally:
        db.close()
