"""Pause scheduled background work while a backup restore replaces the database files.

Each step of a background loop holds a shared ``flock`` on ``<db>.bg-gate.lock``. A restore
first takes ``<db>.bg-intent.lock`` exclusively, so no new step starts, then waits for the
running steps and takes the gate exclusively. After a successful restore the locks stay held
until the panel restarts: the kernel drops them with the process. ``flock`` locks belong to an
open file, so this works between uvicorn workers and between threads of one worker.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, TypeVar

from app.services.long_task_executor import run_long_task

T = TypeVar("T")

logger = logging.getLogger(__name__)

POLL_SECONDS = 0.05
PAUSE_CHECK_SECONDS = 0.5

_gate_db_path: Path | None = None
_pause_fds: list[int] = []
_pause_lock = threading.Lock()


def configure_background_gate(db_path: Path | None) -> None:
    """Enable the gate for the panel DB; without it (tests, scripts) steps run unguarded."""
    global _gate_db_path
    _gate_db_path = db_path


def _lock_paths(db_path: Path) -> tuple[Path, Path]:
    return db_path.with_name(f"{db_path.name}.bg-intent.lock"), db_path.with_name(f"{db_path.name}.bg-gate.lock")


def _try_flock(path: Path, operation: int, *, block: bool = False) -> int | None:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, operation if block else operation | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    except BaseException:
        os.close(fd)
        raise
    return fd


def _unlock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _run_gated(fn: Callable[..., T], args: tuple, kwargs: dict) -> T | None:
    db_path = _gate_db_path
    if db_path is None:
        return fn(*args, **kwargs)
    intent_path, gate_path = _lock_paths(db_path)
    intent_fd = _try_flock(intent_path, fcntl.LOCK_SH)
    if intent_fd is None:
        logger.debug("Background step %s skipped: backup restore in progress", getattr(fn, "__name__", fn))
        return None
    try:
        # A restore takes the gate only while holding the intent lock, so this never waits.
        gate_fd = _try_flock(gate_path, fcntl.LOCK_SH, block=True)
    finally:
        _unlock(intent_fd)
    try:
        return fn(*args, **kwargs)
    finally:
        _unlock(gate_fd)


def background_pause_requested() -> bool:
    """True while a restore waits for running steps; a long step should stop early."""
    db_path = _gate_db_path
    if db_path is None:
        return False
    intent_fd = _try_flock(_lock_paths(db_path)[0], fcntl.LOCK_SH)
    if intent_fd is None:
        return True
    _unlock(intent_fd)
    return False


def sleep_unless_paused(seconds: float) -> bool:
    """Sleep inside a background step; ``False`` as soon as a restore waits for the step."""
    if _gate_db_path is None:
        time.sleep(seconds)
        return True
    remaining = float(seconds)
    while remaining > 0:
        if background_pause_requested():
            return False
        chunk = min(PAUSE_CHECK_SECONDS, remaining)
        time.sleep(chunk)
        remaining -= chunk
    return True


async def run_background_step(fn: Callable[..., T], /, *args, **kwargs) -> T | None:
    """``asyncio.to_thread`` for a background loop step; ``None`` if skipped during a restore."""
    return await asyncio.to_thread(_run_gated, fn, args, kwargs)


async def run_long_background_step(fn: Callable[..., T], /, *args, **kwargs) -> T | None:
    """Same as :func:`run_background_step`, in the long-task pool."""
    return await run_long_task(_run_gated, fn, args, kwargs)


def _flock_until(path: Path, deadline: float) -> int:
    while True:
        fd = _try_flock(path, fcntl.LOCK_EX)
        if fd is not None:
            return fd
        if time.monotonic() >= deadline:
            raise TimeoutError(f"background work did not stop in time ({path.name})")
        time.sleep(POLL_SECONDS)


def pause_background_work(db_path: Path, *, timeout: float) -> None:
    """Stop new background steps and wait for running ones; raise ``TimeoutError`` if they keep running."""
    intent_path, gate_path = _lock_paths(db_path)
    deadline = time.monotonic() + timeout
    intent_fd = _flock_until(intent_path, deadline)
    try:
        gate_fd = _flock_until(gate_path, deadline)
    except BaseException:
        _unlock(intent_fd)
        raise
    with _pause_lock:
        _pause_fds.extend([gate_fd, intent_fd])
    logger.info("Background work paused for backup restore")


def resume_background_work() -> None:
    with _pause_lock:
        fds = list(_pause_fds)
        _pause_fds.clear()
    for fd in fds:
        _unlock(fd)
    if fds:
        logger.info("Background work resumed")
