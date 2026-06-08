"""Background traffic collector task."""

import asyncio
import logging
import time

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
    started = time.perf_counter()
    db = SessionLocal()
    total_wg_runtime_calls = 0
    nodes_processed = 0
    try:
        nodes = db.query(Node).all()
        for node in nodes:
            node_started = time.perf_counter()
            wg_runtime_calls = 0
            clients_changed = 0
            try:
                adapter = get_adapter_for_node(node)
                ovpn = adapter.parse_openvpn_status()
                wg = adapter.parse_wireguard_status()
                status_rows = build_status_rows(ovpn, wg)
                collector = TrafficCollectorService(db, node.id)
                collector.persist_snapshot(status_rows)
                if settings.traffic_limit_reconcile_after_sync:
                    from app.services.traffic_limit_reconcile import reconcile_traffic_limit_policies_safe

                    reconcile_result = reconcile_traffic_limit_policies_safe(db, node_id=node.id)
                    wg_runtime_calls = int(reconcile_result.get("wg_runtime_calls") or 0)
                    clients_changed = int(reconcile_result.get("clients_changed") or 0)
                nodes_processed += 1
                total_wg_runtime_calls += wg_runtime_calls
                logger.info(
                    "Traffic collect node=%s node_id=%d duration_ms=%d wg_runtime_calls=%d clients_changed=%d",
                    node.name,
                    node.id,
                    int((time.perf_counter() - node_started) * 1000),
                    wg_runtime_calls,
                    clients_changed,
                )
            except Exception as exc:
                logger.debug("Traffic collect failed for node %s: %s", node.name, exc)
    finally:
        db.close()
    logger.info(
        "Traffic collect finished nodes=%d duration_ms=%d wg_runtime_calls=%d",
        nodes_processed,
        int((time.perf_counter() - started) * 1000),
        total_wg_runtime_calls,
    )
