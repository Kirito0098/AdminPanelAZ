"""Dedicated event loop thread for Telegram bot updates.

Bot handlers mix awaits with blocking calls (DB, node agents, backup restore).
Running them here keeps the panel's event loop responsive; bot updates wait for
each other instead of every panel request waiting for the bot.

Because a single hung handler blocks every later update, a watchdog logs a stack
trace when a handler runs longer than ``TELEGRAM_BOT_STALL_SECONDS``. It never
interrupts the handler: the stack is the evidence, the admin sees it in Logs.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
import traceback
from collections.abc import Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

BOT_THREAD_NAME = "telegram-bot"

STALL_CHECK_SECONDS = float(os.environ.get("TELEGRAM_BOT_STALL_CHECK_SECONDS", "10"))
STALL_REPORT_SECONDS = float(os.environ.get("TELEGRAM_BOT_STALL_SECONDS", "60"))

_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None

_active_label: str | None = None
_active_started: float | None = None
_reported = False
_watchdog_started = False


def _bot_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    with _lock:
        if _loop is None or _thread is None or not _thread.is_alive():
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, name=BOT_THREAD_NAME, daemon=True)
            thread.start()
            _loop, _thread = loop, thread
        return _loop


def _begin_call(label: str) -> None:
    global _active_label, _active_started, _reported
    with _lock:
        _active_label = label
        _active_started = time.monotonic()
        _reported = False


def _end_call() -> None:
    global _active_label, _active_started, _reported
    with _lock:
        _active_label = None
        _active_started = None
        _reported = False


def _bot_thread_stack() -> str:
    """Stack of the bot loop thread right now — traceback of a stuck handler."""
    thread = _thread
    frame = sys._current_frames().get(thread.ident) if thread and thread.ident else None
    if frame is None:
        return ""
    return "".join(traceback.format_stack(frame))


def check_stall(now: float | None = None) -> str | None:
    """Formatted report when the current bot call runs too long; once per call."""
    global _reported
    with _lock:
        label, started, reported = _active_label, _active_started, _reported
    if label is None or started is None or reported:
        return None
    elapsed = (now if now is not None else time.monotonic()) - started
    if elapsed < STALL_REPORT_SECONDS:
        return None
    with _lock:
        _reported = True
    return (
        f"handler '{label}' runs {elapsed:g}s (threshold {STALL_REPORT_SECONDS:g}s); "
        f"later updates queue behind it\n{_bot_thread_stack()}"
    )


def _watchdog() -> None:
    while True:
        time.sleep(STALL_CHECK_SECONDS)
        try:
            report = check_stall()
        except Exception:  # noqa: BLE001 — the watchdog must never die on its own error
            logger.exception("telegram bot stall check failed")
            continue
        if report:
            logger.error("TELEGRAM BOT STALL: %s", report)


def _start_watchdog() -> None:
    global _watchdog_started
    with _lock:
        if _watchdog_started:
            return
        _watchdog_started = True
    threading.Thread(target=_watchdog, name="telegram-bot-watchdog", daemon=True).start()


async def run_on_bot_loop(coro: Coroutine[Any, Any, T]) -> T:
    _start_watchdog()
    _begin_call(getattr(coro, "__qualname__", type(coro).__name__))
    try:
        future = asyncio.run_coroutine_threadsafe(coro, _bot_loop())
        # Telegram may drop a slow webhook request; a started restore or reboot must still finish.
        return await asyncio.shield(asyncio.wrap_future(future))
    finally:
        _end_call()

