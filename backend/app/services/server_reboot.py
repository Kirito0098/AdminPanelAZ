"""Scheduled OS reboot with cancel window (in-memory; not durable across process restart)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Callable

DELAY_SECONDS = 15
CONFIRM_PHRASE = "REBOOT"

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
    status: str  # pending | cancelled | executed | failed


_lock = threading.Lock()
_pending: dict[str, PendingReboot] = {}
_node_index: dict[int, str] = {}
_timers: dict[str, threading.Timer] = {}
_execute_fns: dict[str, ExecuteFn] = {}


def clear_all_for_tests() -> None:
    with _lock:
        for t in _timers.values():
            t.cancel()
        _pending.clear()
        _node_index.clear()
        _timers.clear()
        _execute_fns.clear()


def list_pending() -> list[PendingReboot]:
    with _lock:
        return [replace(p) for p in _pending.values() if p.status == "pending"]


def get_pending(reboot_id: str) -> PendingReboot | None:
    with _lock:
        p = _pending.get(reboot_id)
        return replace(p) if p else None


def schedule_reboot(
    *,
    node_id: int,
    node_name: str,
    scheduled_by: str,
    execute_fn: ExecuteFn | None = None,
    delay_seconds: float | None = None,
) -> PendingReboot:
    delay = float(DELAY_SECONDS if delay_seconds is None else delay_seconds)
    now = datetime.now(timezone.utc)
    reboot_id = str(uuid.uuid4())
    pending = PendingReboot(
        reboot_id=reboot_id,
        node_id=node_id,
        node_name=node_name,
        scheduled_by=scheduled_by,
        created_at=now,
        execute_at=now + timedelta(seconds=delay),
        status="pending",
    )

    def _run() -> None:
        with _lock:
            current = _pending.get(reboot_id)
            if current is None or current.status != "pending":
                return
            fn = _execute_fns.pop(reboot_id, None)
            _timers.pop(reboot_id, None)
            claimed = replace(current, status="executing")
            _pending[reboot_id] = claimed
        status = "executed"
        try:
            if fn is not None:
                fn(claimed)
        except Exception:
            status = "failed"
        with _lock:
            current = _pending.get(reboot_id)
            if current is None or current.status != "executing":
                return
            _pending[reboot_id] = replace(current, status=status)
            _node_index.pop(node_id, None)

    with _lock:
        if node_id in _node_index:
            raise RebootError("duplicate_pending", "Перезагрузка этого узла уже запланирована")
        _pending[reboot_id] = pending
        _node_index[node_id] = reboot_id
        if execute_fn is not None:
            _execute_fns[reboot_id] = execute_fn
        timer = threading.Timer(delay, _run)
        timer.daemon = True
        _timers[reboot_id] = timer
        timer.start()
    return replace(pending)


def cancel_reboot(reboot_id: str) -> PendingReboot:
    with _lock:
        current = _pending.get(reboot_id)
        if current is None:
            raise RebootError("not_found", "Запланированная перезагрузка не найдена")
        if current.status != "pending":
            raise RebootError("not_cancellable", "Перезагрузку уже нельзя отменить")
        timer = _timers.pop(reboot_id, None)
        if timer is not None:
            timer.cancel()
        updated = replace(current, status="cancelled")
        _pending[reboot_id] = updated
        _node_index.pop(current.node_id, None)
        _execute_fns.pop(reboot_id, None)
        return replace(updated)
