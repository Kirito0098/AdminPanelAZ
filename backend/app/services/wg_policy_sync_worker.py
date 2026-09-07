"""Background WG/AWG access policy sync worker (ported from AdminAntizapret wg_awg_policy_sync)."""

import asyncio
import logging
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node, WgAccessPolicy
from app.services.access_policy import AccessPolicyService
from app.services.node_manager import _is_vpn_node, get_adapter_for_node, node_metadata_dict

logger = logging.getLogger(__name__)
_startup_full_sync_done = False


def _is_wg_policy_sync_enabled() -> bool:
    """Runtime gate — WG_POLICY_SYNC_ENABLED / wg_policy_sync can flip without restart."""
    from app.services.feature_guards import get_feature_service

    return get_feature_service().is_enabled("wg_policy_sync")


def reconcile_wg_policies_for_all_nodes(db: Session, *, sync_all_runtime: bool = False) -> dict:
    total_blocked = 0
    total_unblocked = 0
    nodes_processed = 0
    total_wg_runtime_calls = 0
    total_clients_changed = 0
    nodes_skipped_empty = 0
    for node in db.query(Node).all():
        if not _is_vpn_node(node):
            continue
        # Avoid adapter/SSH setup when the node has no WG policy rows to reconcile.
        if not sync_all_runtime:
            has_policy = (
                db.query(WgAccessPolicy.id)
                .filter(WgAccessPolicy.node_id == node.id)
                .limit(1)
                .first()
            )
            if has_policy is None:
                nodes_skipped_empty += 1
                continue
        result = _reconcile_for_node(db, node, sync_all_runtime=sync_all_runtime)
        if result.get("wg_policy_reconcile") == "ok":
            nodes_processed += 1
            total_blocked += len(result.get("blocked_clients") or [])
            total_unblocked += len(result.get("unblocked_clients") or [])
            total_wg_runtime_calls += int(result.get("wg_runtime_calls") or 0)
            total_clients_changed += int(result.get("clients_changed") or 0)
    return {
        "wg_policy_sync": "ok",
        "nodes_processed": nodes_processed,
        "nodes_skipped_empty": nodes_skipped_empty,
        "blocked_clients": total_blocked,
        "unblocked_clients": total_unblocked,
        "wg_runtime_calls": total_wg_runtime_calls,
        "clients_changed": total_clients_changed,
    }


def _reconcile_for_node(db: Session, node: Node, *, sync_all_runtime: bool = False) -> dict:
    settings = get_settings()
    meta = node_metadata_dict(node)
    antizapret_path = Path(str(meta.get("antizapret_path") or settings.antizapret_path))
    svc = AccessPolicyService(
        db,
        antizapret_path=antizapret_path,
        node_id=node.id,
        adapter=get_adapter_for_node(node),
    )
    return svc.reconcile_all_wg_policies(
        apply_runtime=True,
        node_id=node.id,
        sync_all_runtime=sync_all_runtime,
    )


def reconcile_wg_policies_safe(db: Session, *, sync_all_runtime: bool = False) -> dict:
    try:
        return reconcile_wg_policies_for_all_nodes(db, sync_all_runtime=sync_all_runtime)
    except Exception as exc:
        logger.warning("WG policy sync failed: %s", exc)
        return {"wg_policy_sync": "error", "error": str(exc)}


def _reconcile_all_nodes_once(*, sync_all_runtime: bool = False) -> None:
    started = time.perf_counter()
    db = SessionLocal()
    try:
        result = reconcile_wg_policies_safe(db, sync_all_runtime=sync_all_runtime)
        if result.get("wg_policy_sync") == "ok":
            logger.info(
                "WG policy sync: nodes=%d skipped_empty=%d blocked=%d unblocked=%d "
                "clients_changed=%d wg_runtime_calls=%d duration_ms=%d sync_all_runtime=%s",
                result.get("nodes_processed", 0),
                result.get("nodes_skipped_empty", 0),
                result.get("blocked_clients", 0),
                result.get("unblocked_clients", 0),
                result.get("clients_changed", 0),
                result.get("wg_runtime_calls", 0),
                int((time.perf_counter() - started) * 1000),
                sync_all_runtime,
            )
    finally:
        db.close()


async def run_wg_policy_sync_loop() -> None:
    """Policy sync loop — re-checks wg_policy_sync each tick (toggle can flip without restart)."""
    global _startup_full_sync_done

    while True:
        settings = get_settings()
        interval = max(30, int(settings.wg_policy_sync_interval_seconds or 120))
        try:
            if not _is_wg_policy_sync_enabled():
                logger.debug("wg_policy_sync skipped — wg_policy_sync disabled")
            else:
                if not _startup_full_sync_done:
                    await asyncio.to_thread(_reconcile_all_nodes_once, sync_all_runtime=True)
                    _startup_full_sync_done = True
                else:
                    await asyncio.to_thread(_reconcile_all_nodes_once, sync_all_runtime=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("WG policy sync error: %s", exc)
        await asyncio.sleep(interval)
