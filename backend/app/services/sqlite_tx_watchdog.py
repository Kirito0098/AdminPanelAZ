"""Watchdog: открытая транзакция записи SQLite, которая живёт слишком долго.

SQLite пускает одного писателя. Если транзакция записи держится долго (а тем
более через сетевой вызов к узлу), все остальные писатели панели получают
``database is locked`` после ``busy_timeout`` — со стороны это выглядит как
«панель упала» и ловится только руками через py-spy.

Watchdog пишет в журнал стек потока-держателя **пока транзакция ещё открыта**,
чтобы виновником была конкретная строка кода, а не «панель недоступна».
Поведение не меняет: только записи в журнал.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import traceback
from typing import Any

logger = logging.getLogger(__name__)

CHECK_SECONDS = float(os.environ.get("SQLITE_TX_WATCH_CHECK_SECONDS", "5"))
WARN_SECONDS = float(os.environ.get("SQLITE_TX_WARN_SECONDS", "5"))

_WRITE_WORDS = ("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP")

_lock = threading.Lock()
_active: dict[int, tuple[float, str]] = {}
_reported: set[int] = set()
_started = False


def _is_write_statement(statement: str) -> bool:
    head = (statement or "").lstrip()[:8].upper()
    return any(head.startswith(word) for word in _WRITE_WORDS)


def mark_write_started(statement: str, *, now: float | None = None) -> None:
    """Remember the first write of the current thread's transaction."""
    ident = threading.get_ident()
    with _lock:
        if ident in _active:
            return
        started = now if now is not None else time.monotonic()
        _active[ident] = (started, " ".join((statement or "").split())[:200])
        _reported.discard(ident)


def mark_write_finished() -> float:
    """Close the current thread's transaction; return its duration in seconds."""
    ident = threading.get_ident()
    with _lock:
        entry = _active.pop(ident, None)
        _reported.discard(ident)
    if entry is None:
        return 0.0
    return time.monotonic() - entry[0]


def _thread_stack(ident: int) -> str:
    frame = sys._current_frames().get(ident)
    if frame is None:
        return ""
    return "".join(traceback.format_stack(frame))


def check_stalls(*, now: float | None = None) -> list[str]:
    """Reports for long write transactions; one report per transaction."""
    current = now if now is not None else time.monotonic()
    with _lock:
        stale = [
            (ident, current - started, statement)
            for ident, (started, statement) in _active.items()
            if current - started >= WARN_SECONDS and ident not in _reported
        ]
        for ident, _elapsed, _statement in stale:
            _reported.add(ident)
    return [
        f"SQLite write transaction open {elapsed:.0f}s in thread {ident}: {statement}\n"
        f"{_thread_stack(ident)}"
        for ident, elapsed, statement in stale
    ]


def _watchdog() -> None:
    while True:
        time.sleep(CHECK_SECONDS)
        try:
            for report in check_stalls():
                logger.error("SLOW SQLITE WRITE: %s", report)
        except Exception:  # noqa: BLE001 — watchdog must never die on its own error
            logger.exception("sqlite write watchdog check failed")


def start_watchdog() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_watchdog, name="sqlite-write-watchdog", daemon=True).start()


def install(engine: Any) -> None:
    """Attach SQLAlchemy events to ``engine`` and start the reporter thread."""
    from sqlalchemy import event

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if _is_write_statement(statement):
            mark_write_started(statement)

    @event.listens_for(engine, "commit")
    def _on_commit(conn):  # noqa: ANN001
        elapsed = mark_write_finished()
        if elapsed >= WARN_SECONDS:
            logger.warning("SQLite write transaction took %.0fs: %s", elapsed, _thread_stack_names())

    @event.listens_for(engine, "rollback")
    def _on_rollback(conn):  # noqa: ANN001
        mark_write_finished()

    start_watchdog()


def _thread_stack_names() -> str:
    frame = sys._current_frames().get(threading.get_ident())
    if frame is None:
        return ""
    names = [f"{f.name}:{f.lineno}" for f in traceback.extract_stack(frame)[-6:]]
    return " <- ".join(reversed(names))
