"""Keep an HA group out of ``pending`` once its sync task has ended.

``pending`` blocks new setup / shared-domain runs (409) and auto-heal, so a task that raised
or died with the panel process must not leave it behind.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session

from app.models import BackgroundTask, NodeSyncGroup, SyncStatus

logger = logging.getLogger(__name__)

ACTIVE_TASK_STATUSES = ("queued", "running")
ERROR_MAX_LEN = 1000
REPLICA_DRIFT_HINT = (
    "Файлы на реплику скопированы, но WireGuard / AZ-AWG2 их не применил: "
    "проверьте реплику и нажмите «Синхронизировать»"
)


def mark_group_sync_failed(db: Session, group_id: int, error: str) -> None:
    db.rollback()
    group = db.get(NodeSyncGroup, group_id)
    if group is None:
        return
    group.sync_status = SyncStatus.failed
    group.last_sync_error = error[:ERROR_MAX_LEN]
    db.commit()


def group_is_pending(db: Session, group: NodeSyncGroup) -> bool:
    """Committed status, not the loaded copy: a setup / Push full may have started meanwhile."""
    status = db.query(NodeSyncGroup.sync_status).filter(NodeSyncGroup.id == group.id).scalar()
    return status == SyncStatus.pending


def notify_replica_drift(db: Session, group: NodeSyncGroup, drifts: list[dict[str, Any]]) -> None:
    """Same admin event as the reconcile drift; a failed notify must not undo the replication."""
    try:
        from app.services.admin_notify import admin_notify_service

        summary = "; ".join(f"{item.get('node_name') or item.get('node_id')}: {item.get('error')}" for item in drifts)
        admin_notify_service.send(
            db,
            "node_sync_drift",
            details=json.dumps(
                {
                    "group_id": group.id,
                    "name": group.name,
                    "shared_domain": group.shared_domain,
                    "summary": summary[:ERROR_MAX_LEN],
                    "hint": REPLICA_DRIFT_HINT,
                },
                ensure_ascii=False,
            ),
        )
    except Exception as exc:
        logger.warning("HA replica drift notify failed for group %s: %s", group.id, exc)


@contextmanager
def fail_group_on_error(db: Session, group_id: int) -> Iterator[None]:
    """Mark the group failed if the block raises; the exception still fails the task."""
    try:
        yield
    except BaseException as exc:
        try:
            mark_group_sync_failed(db, group_id, str(exc) or type(exc).__name__)
        except Exception:
            logger.exception("Could not mark sync group %s as failed", group_id)
        raise


def recover_stuck_pending_groups(db: Session) -> int:
    recovered = 0
    for group in db.query(NodeSyncGroup).filter(NodeSyncGroup.sync_status == SyncStatus.pending).all():
        task = db.get(BackgroundTask, group.last_sync_task_id) if group.last_sync_task_id else None
        if task is not None and task.status in ACTIVE_TASK_STATUSES:
            continue
        group.sync_status = SyncStatus.failed
        detail = (task.error if task is not None else None) or "задача синхронизации завершилась без итогового статуса"
        group.last_sync_error = f"Синхронизация не завершилась: {detail}"[:ERROR_MAX_LEN]
        recovered += 1
    if recovered:
        db.commit()
    return recovered


def recover_stuck_pending_groups_once() -> int:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        return recover_stuck_pending_groups(db)
    finally:
        db.close()
