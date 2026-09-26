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
from app.models import Node, NodeStatus, OpenVpnBufferGuardSettings
from app.services.node_manager import get_adapter_for_node
from app.services.openvpn_buffer_guard import (
    BufferGuardAgentOutdated,
    process_temp_ban_expiries,
    run_guard_pass,
)
from app.services.background_gate import background_pause_requested, run_background_step

logger = logging.getLogger(__name__)

WORKER_INTERVAL_SECONDS = 20

# Nodes already reported as running an agent without Buffer Guard (warn once per process).
_outdated_agent_nodes: set[int] = set()


def _online_nodes_with_enabled_settings(db: Session) -> list[Node]:
    # Только чтение: строка настроек без явного включения охраны не нужна.
    return (
        db.query(Node)
        .join(OpenVpnBufferGuardSettings, OpenVpnBufferGuardSettings.node_id == Node.id)
        .filter(Node.status == NodeStatus.online, OpenVpnBufferGuardSettings.enabled.is_(True))
        .order_by(Node.id.asc())
        .all()
    )


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
            if background_pause_requested():
                break
            try:
                adapter = get_adapter_for_node(node)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("openvpn_buffer_guard: adapter for node %s failed: %s", node.id, exc)
                continue

            try:
                results = run_guard_pass(db, adapter, node.id, manual=False)
                _outdated_agent_nodes.discard(node.id)
                if results:
                    triggered = sum(1 for item in results if item.get("threshold_exceeded"))
                    if triggered:
                        logger.info(
                            "openvpn_buffer_guard: node_id=%s units=%s threshold_exceeded=%s",
                            node.id,
                            len(results),
                            triggered,
                        )
            except BufferGuardAgentOutdated as exc:
                if node.id not in _outdated_agent_nodes:
                    _outdated_agent_nodes.add(node.id)
                    logger.warning("openvpn_buffer_guard: node %s (%s): %s", node.id, node.name, exc)
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

