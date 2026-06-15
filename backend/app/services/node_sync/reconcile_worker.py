"""Background Node Sync reconcile worker — periodic parity checks."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from app.config import get_settings
from app.database import SessionLocal
from app.models import NodeSyncGroup, SyncStatus
from app.services.node_sync.verify import verify_sync_group

logger = logging.getLogger(__name__)
settings = get_settings()


def reconcile_sync_groups_once() -> dict:
    db = SessionLocal()
    checked = 0
    drift_groups: list[dict] = []
    try:
        groups = db.query(NodeSyncGroup).order_by(NodeSyncGroup.id).all()
        for group in groups:
            result = verify_sync_group(db, group)
            checked += 1
            if result.get("ready"):
                continue
            group.sync_status = SyncStatus.failed
            group.last_sync_error = str(result.get("summary") or "parity mismatch")
            db.commit()
            drift_groups.append(
                {
                    "group_id": group.id,
                    "name": group.name,
                    "shared_domain": group.shared_domain,
                    "summary": result.get("summary"),
                }
            )
            logger.warning(
                "Node sync drift: group=%s domain=%s summary=%s",
                group.name,
                group.shared_domain,
                result.get("summary"),
            )
        return {"node_sync_reconcile": "ok", "checked": checked, "drift": drift_groups}
    except Exception as exc:
        logger.warning("Node sync reconcile failed: %s", exc)
        return {"node_sync_reconcile": "error", "error": str(exc)}
    finally:
        db.close()


def reconcile_sync_groups_safe() -> dict:
    started = time.perf_counter()
    result = reconcile_sync_groups_once()
    if result.get("node_sync_reconcile") == "ok":
        drift = result.get("drift") or []
        logger.info(
            "Node sync reconcile: checked=%d drift=%d duration_ms=%d",
            result.get("checked", 0),
            len(drift),
            int((time.perf_counter() - started) * 1000),
        )
        if drift:
            _notify_drift(drift)
    return result


def _notify_drift(drift_groups: list[dict]) -> None:
    try:
        from app.services.admin_notify import admin_notify_service

        db = SessionLocal()
        try:
            for item in drift_groups:
                admin_notify_service.send_settings_change(
                    db,
                    actor_username="system",
                    settings_key="node_sync_drift",
                    detail=json.dumps(item, ensure_ascii=False),
                )
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Node sync drift notify skipped: %s", exc)


async def run_node_sync_reconcile_loop() -> None:
    if not settings.node_sync_reconcile_enabled:
        return

    while True:
        try:
            await asyncio.to_thread(reconcile_sync_groups_safe)
        except Exception as exc:
            logger.warning("Node sync reconcile loop error: %s", exc)
        await asyncio.sleep(settings.node_sync_reconcile_interval_seconds)
