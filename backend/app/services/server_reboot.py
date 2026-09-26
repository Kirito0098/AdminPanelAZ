"""Scheduled OS reboot with cancel window.

State lives in ``server_reboot_requests`` so any uvicorn worker can list or cancel
it; the timer and execute callback stay in the worker that scheduled the reboot.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import ServerRebootRecord
from app.services.process_identity import current_process_owner, is_owner_alive

logger = logging.getLogger(__name__)

DELAY_SECONDS = 15
CONFIRM_PHRASE = "REBOOT"
# A pending reboot this far past its time will not be run by its timer, even if the worker lives.
ABANDONED_AFTER = timedelta(minutes=2)

ACTIVE_STATUSES = ("pending", "executing")

ExecuteFn = Callable[["PendingReboot"], None]


class RebootError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PendingReboot:
    reboot_id: str
    node_id: int
    node_name: str
    scheduled_by: str
    created_at: datetime
    execute_at: datetime
    status: str  # pending | executing | cancelled | executed | failed | interrupted


_lock = threading.Lock()
_timers: dict[str, threading.Timer] = {}
_execute_fns: dict[str, ExecuteFn] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_pending(row: ServerRebootRecord) -> PendingReboot:
    return PendingReboot(
        reboot_id=row.id,
        node_id=row.node_id,
        node_name=row.node_name,
        scheduled_by=row.scheduled_by,
        created_at=row.created_at.replace(tzinfo=timezone.utc),
        execute_at=row.execute_at.replace(tzinfo=timezone.utc),
        status=row.status,
    )


def _set_status(reboot_id: str, *, expected: str, new: str) -> bool:
    db = SessionLocal()
    try:
        changed = (
            db.query(ServerRebootRecord)
            .filter(ServerRebootRecord.id == reboot_id, ServerRebootRecord.status == expected)
            .update({ServerRebootRecord.status: new}, synchronize_session=False)
        )
        db.commit()
        return changed == 1
    finally:
        db.close()


def _is_abandoned(row: ServerRebootRecord, now: datetime) -> bool:
    if not is_owner_alive(row.owner):
        return True
    return row.status == "pending" and row.execute_at < now - ABANDONED_AFTER


def _interrupt_abandoned(db) -> int:
    now = _utcnow()
    rows = db.query(ServerRebootRecord).filter(ServerRebootRecord.status.in_(ACTIVE_STATUSES)).all()
    ids = [row.id for row in rows if _is_abandoned(row, now)]
    if not ids:
        return 0
    return (
        db.query(ServerRebootRecord)
        .filter(ServerRebootRecord.id.in_(ids), ServerRebootRecord.status.in_(ACTIVE_STATUSES))
        .update({ServerRebootRecord.status: "interrupted"}, synchronize_session=False)
    )


def clear_all_for_tests() -> None:
    with _lock:
        for t in _timers.values():
            t.cancel()
        _timers.clear()
        _execute_fns.clear()
    db = SessionLocal()
    try:
        db.query(ServerRebootRecord).delete()
        db.commit()
    finally:
        db.close()


def interrupt_abandoned_reboots() -> int:
    """Timers die with their worker; free the nodes for new reboots."""
    db = SessionLocal()
    try:
        count = _interrupt_abandoned(db)
        db.commit()
        return count
    finally:
        db.close()


def list_pending() -> list[PendingReboot]:
    db = SessionLocal()
    try:
        now = _utcnow()
        rows = (
            db.query(ServerRebootRecord)
            .filter(ServerRebootRecord.status == "pending")
            .order_by(ServerRebootRecord.execute_at)
            .all()
        )
        return [_to_pending(row) for row in rows if not _is_abandoned(row, now)]
    finally:
        db.close()


def get_pending(reboot_id: str) -> PendingReboot | None:
    db = SessionLocal()
    try:
        row = db.get(ServerRebootRecord, reboot_id)
        return _to_pending(row) if row else None
    finally:
        db.close()


def schedule_reboot(
    *,
    node_id: int,
    node_name: str,
    scheduled_by: str,
    execute_fn: ExecuteFn | None = None,
    delay_seconds: float | None = None,
) -> PendingReboot:
    delay = float(DELAY_SECONDS if delay_seconds is None else delay_seconds)
    now = _utcnow()
    row = ServerRebootRecord(
        id=str(uuid.uuid4()),
        node_id=node_id,
        node_name=node_name,
        scheduled_by=scheduled_by,
        created_at=now,
        execute_at=now + timedelta(seconds=delay),
        status="pending",
        owner=current_process_owner(),
    )
    db = SessionLocal()
    try:
        _interrupt_abandoned(db)
        db.add(row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise RebootError("duplicate_pending", "Перезагрузка этого узла уже запланирована") from exc
        pending = _to_pending(row)
    finally:
        db.close()
    reboot_id = pending.reboot_id

    def _run() -> None:
        with _lock:
            fn = _execute_fns.pop(reboot_id, None)
            _timers.pop(reboot_id, None)
        try:
            if not _set_status(reboot_id, expected="pending", new="executing"):
                return
            status = "executed"
            try:
                if fn is not None:
                    fn(replace(pending, status="executing"))
            except Exception:
                logger.exception("Scheduled reboot of %s failed", pending.node_name)
                status = "failed"
            _set_status(reboot_id, expected="executing", new=status)
        except Exception:
            logger.exception("Scheduled reboot of %s: state update failed", pending.node_name)

    with _lock:
        if execute_fn is not None:
            _execute_fns[reboot_id] = execute_fn
        timer = threading.Timer(delay, _run)
        timer.daemon = True
        _timers[reboot_id] = timer
        timer.start()
    return pending


def cancel_reboot(reboot_id: str) -> PendingReboot:
    current = get_pending(reboot_id)
    if current is None:
        raise RebootError("not_found", "Запланированная перезагрузка не найдена")
    if not _set_status(reboot_id, expected="pending", new="cancelled"):
        raise RebootError("not_cancellable", "Перезагрузку уже нельзя отменить")
    with _lock:
        timer = _timers.pop(reboot_id, None)
        _execute_fns.pop(reboot_id, None)
    if timer is not None:
        timer.cancel()
    return replace(current, status="cancelled")
