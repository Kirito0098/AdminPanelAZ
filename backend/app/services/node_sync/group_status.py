"""Keep an HA group out of ``pending`` once its sync task has ended.

``pending`` blocks new setup / shared-domain runs (409) and auto-heal, so a task that raised
or died with the panel process must not leave it behind.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.models import BackgroundTask, NodeSyncGroup, SyncStatus

logger = logging.getLogger(__name__)

ACTIVE_TASK_STATUSES = ("queued", "running")
ERROR_MAX_LEN = 1000


def mark_group_sync_failed(db: Session, group_id: int, error: str) -> None:
    db.rollback()
    group = db.get(NodeSyncGroup, group_id)
    if group is None:
        return
    group.sync_status = SyncStatus.failed
    group.last_sync_error = error[:ERROR_MAX_LEN]
    db.commit()


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
