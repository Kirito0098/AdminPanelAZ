"""Background worker for OpenVPN Buffer Guard.

Every 20 seconds:
 - iterates online nodes,
 - filters nodes with buffer guard enabled,
 - runs one guard pass per node,
 - then processes temporary ban expiries.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Node, NodeStatus
from app.services.node_manager import get_adapter_for_node
from app.services.openvpn_buffer_guard import (
    get_settings as get_guard_settings,
    process_temp_ban_expiries,
    run_guard_pass,
)
from app.services.background_gate import run_background_step

logger = logging.getLogger(__name__)

WORKER_INTERVAL_SECONDS = 20


def _online_nodes_with_enabled_settings(db: Session) -> list[Node]:
    nodes = (
        db.query(Node)
        .filter(Node.status == NodeStatus.online)
        .order_by(Node.id.asc())
        .all()
    )
    enabled: list[Node] = []
    for node in nodes:
        try:
            settings_row = get_guard_settings(db, node.id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("openvpn_buffer_guard: failed to load settings for node %s: %s", node.id, exc)
            continue
        if settings_row.enabled:
            enabled.append(node)
    return enabled


def _run_once() -> None:
    db = SessionLocal()
    try:
        nodes = _online_nodes_with_enabled_settings(db)
        if not nodes:
            # Still clear any expired bans (in case settings were toggled off).
            try:
                process_temp_ban_expiries(db)
            except Exception:  # pragma: no cover - defensive
                logger.exception("openvpn_buffer_guard: temp ban expiry processing failed")
            return

        for node in nodes:
            try:
                adapter = get_adapter_for_node(node)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("openvpn_buffer_guard: adapter for node %s failed: %s", node.id, exc)
                continue

            try:
                results = run_guard_pass(db, adapter, node.id, manual=False)
                if results:
                    triggered = sum(1 for item in results if item.get("threshold_exceeded"))
                    if triggered:
                        logger.info(
                            "openvpn_buffer_guard: node_id=%s units=%s threshold_exceeded=%s",
                            node.id,
                            len(results),
                            triggered,
                        )
            except Exception:  # pragma: no cover - defensive
                logger.exception("openvpn_buffer_guard: guard pass failed for node %s", node.id)

        try:
            process_temp_ban_expiries(db)
        except Exception:  # pragma: no cover - defensive
            logger.exception("openvpn_buffer_guard: temp ban expiry processing failed")
    finally:
        db.close()


async def run_openvpn_buffer_guard_loop() -> None:
    """Main asyncio loop for the buffer guard worker."""
    while True:
        try:
            await run_background_step(_run_once)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive
            logger.exception("openvpn buffer guard tick failed")
        await asyncio.sleep(WORKER_INTERVAL_SECONDS)

