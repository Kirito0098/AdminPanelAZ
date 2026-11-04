"""Serialize panel → remote node-agent requests per host:port.

One in-flight request per remote endpoint (HTTPS+mTLS or HTTP). Nested calls on the
same thread re-enter. Background workers set nonblocking mode and skip a busy node
instead of queueing behind a long create. Interactive requests wait at most
``WAIT_TIMEOUT_SECONDS`` and then raise ``NodeHttpTimeout``: the panel shows
"узел занят" instead of hanging the request thread for minutes.

Multi-minute admin work (patch build, backups, config apply) and the Telegram relay
run inside ``node_http_gate_bypass`` — holding the slot for their whole duration
would stall every other call to the same node.
"""

from __future__ import annotations

import fcntl
import hashlib
import logging
import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

# How long one interactive request waits for the node slot before failing with node_busy.
WAIT_TIMEOUT_SECONDS = 20.0
_FLOCK_POLL_SECONDS = 0.02

_wait: ContextVar[bool] = ContextVar("node_http_gate_wait", default=True)
_bypass: ContextVar[bool] = ContextVar("node_http_gate_bypass", default=False)
_locks_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}
_thread_depth = threading.local()
_lock_dir: Path | None = None


class NodeHttpBusy(Exception):
    """Remote node HTTP slot is held; nonblocking caller should skip this node."""


class NodeHttpTimeout(Exception):
    """Interactive caller waited ``WAIT_TIMEOUT_SECONDS`` for the slot and gave up."""


def configure_node_http_gate(db_path: Path | None) -> None:
    """Enable cross-worker flock files next to the panel DB; None disables them."""
    global _lock_dir
    if db_path is None:
        _lock_dir = None
        return
    path = db_path.parent / f"{db_path.name}.node-http-gates"
    path.mkdir(mode=0o700, exist_ok=True)
    _lock_dir = path


def node_http_gate_key(host: str, port: int) -> str:
    return f"{host}:{int(port)}"


@contextmanager
def node_http_gate_nonblocking() -> Iterator[None]:
    """Background polls: try_acquire; raise NodeHttpBusy from adapter if held."""
    token = _wait.set(False)
    try:
        yield
    finally:
        _wait.reset(token)


@contextmanager
def node_http_gate_bypass() -> Iterator[None]:
    """Long admin operations and the Telegram relay: never take the per-node slot."""
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


def _rlock_for(key: str) -> threading.RLock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _locks[key] = lock
        return lock


def _depths() -> dict[str, int]:
    depths = getattr(_thread_depth, "depths", None)
    if depths is None:
        depths = {}
        _thread_depth.depths = depths
    return depths


def _flock_path(key: str) -> Path | None:
    if _lock_dir is None:
        return None
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return _lock_dir / f"{digest}.lock"


def _open_flock(key: str, *, wait: bool, deadline: float | None) -> int | None:
    """Take the cross-worker flock; ``NodeHttpBusy``/``NodeHttpTimeout`` when denied."""
    path = _flock_path(key)
    if path is None:
        return None
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if not wait:
                os.close(fd)
                raise NodeHttpBusy(key) from None
            if deadline is not None and time.monotonic() >= deadline:
                os.close(fd)
                raise NodeHttpTimeout(key) from None
            time.sleep(_FLOCK_POLL_SECONDS)


@contextmanager
def hold_node_http(key: str) -> Iterator[None]:
    """Hold the per-node slot for the duration of one adapter request (reentrant)."""
    if _bypass.get():
        yield
        return

    wait = bool(_wait.get())
    depths = _depths()
    depth = depths.get(key, 0)
    if depth > 0:
        depths[key] = depth + 1
        try:
            yield
        finally:
            depths[key] = depths[key] - 1
            if depths[key] <= 0:
                depths.pop(key, None)
        return

    deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS if wait else None
    lock = _rlock_for(key)
    if wait:
        acquired = lock.acquire(timeout=WAIT_TIMEOUT_SECONDS)
        if not acquired:
            raise NodeHttpTimeout(key)
    else:
        acquired = lock.acquire(blocking=False)
        if not acquired:
            raise NodeHttpBusy(key)

    flock_fd: int | None = None
    try:
        flock_fd = _open_flock(key, wait=wait, deadline=deadline)
        depths[key] = 1
        try:
            yield
        finally:
            depths[key] = depths.get(key, 1) - 1
            if depths[key] <= 0:
                depths.pop(key, None)
    finally:
        if flock_fd is not None:
            try:
                fcntl.flock(flock_fd, fcntl.LOCK_UN)
            finally:
                os.close(flock_fd)
        lock.release()
