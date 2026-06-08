"""Background WG/AWG access policy sync worker (ported from AdminAntizapret wg_awg_policy_sync)."""

import asyncio
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node
from app.services.access_policy import AccessPolicyService
from app.services.node_manager import get_adapter_for_node, node_metadata_dict

logger = logging.getLogger(__name__)
settings = get_settings()


def reconcile_wg_policies_for_all_nodes(db: Session) -> dict:
    total_blocked = 0
    total_unblocked = 0
    nodes_processed = 0
    for node in db.query(Node).all():
        result = _reconcile_for_node(db, node)
        if result.get("wg_policy_reconcile") == "ok":
            nodes_processed += 1
            total_blocked += len(result.get("blocked_clients") or [])
            total_unblocked += len(result.get("unblocked_clients") or [])
    return {
        "wg_policy_sync": "ok",
        "nodes_processed": nodes_processed,
        "blocked_clients": total_blocked,
        "unblocked_clients": total_unblocked,
    }


def _reconcile_for_node(db: Session, node: Node) -> dict:
    meta = node_metadata_dict(node)
    antizapret_path = Path(str(meta.get("antizapret_path") or settings.antizapret_path))
    svc = AccessPolicyService(
        db,
        antizapret_path=antizapret_path,
        node_id=node.id,
        adapter=get_adapter_for_node(node),
    )
    return svc.reconcile_all_wg_policies(apply_runtime=True, node_id=node.id)


def reconcile_wg_policies_safe(db: Session) -> dict:
    try:
        return reconcile_wg_policies_for_all_nodes(db)
    except Exception as exc:
        logger.warning("WG policy sync failed: %s", exc)
        return {"wg_policy_sync": "error", "error": str(exc)}


def _reconcile_all_nodes_once() -> None:
    db = SessionLocal()
    try:
        result = reconcile_wg_policies_safe(db)
        if result.get("wg_policy_sync") == "ok":
            logger.info(
                "WG policy sync: nodes=%d blocked=%d unblocked=%d",
                result.get("nodes_processed", 0),
                result.get("blocked_clients", 0),
                result.get("unblocked_clients", 0),
            )
    finally:
        db.close()


async def run_wg_policy_sync_loop() -> None:
    if not settings.wg_policy_sync_enabled:
        return

    try:
        await asyncio.to_thread(_reconcile_all_nodes_once)
    except Exception as exc:
        logger.warning("WG policy sync startup reconcile failed: %s", exc)

    while True:
        try:
            await asyncio.to_thread(_reconcile_all_nodes_once)
        except Exception as exc:
            logger.warning("WG policy sync error: %s", exc)
        await asyncio.sleep(settings.wg_policy_sync_interval_seconds)
