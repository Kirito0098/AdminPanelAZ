"""Single apply pipeline: sync providers → doall.sh → client profiles → multihome.

Routing apply, manual doall and the CIDR deploy used to run these steps with
their own order, progress texts and result keys. The order is fixed here:

    sync → doall → recreate profiles → openvpn multihome

The steps run under :func:`apply_slot`: one heavy apply per node at a time. The
enqueue guards (``HEAVY_APPLY_TASK_TYPES`` in ``background_tasks``) reject a
second task up front; the slot covers the window between that guard and the
actual run, and direct callers that never enqueue a task.

Known limitation: the slot is a process lock, which covers the single uvicorn
worker in production (tasks run in its ``ThreadPoolExecutor``). A multi-worker
deployment would need a DB-level lock.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from fastapi import HTTPException

from app.services.openvpn_multihome import maybe_ensure_openvpn_multihome
from app.services.openvpn_profile_repair import recreate_openvpn_profiles

ProgressCallback = Callable[[int, str, str | None], None]

APPLY_BUSY_MESSAGE = "Применение конфигурации уже выполняется"
# Default key: callers that cannot name the node still share one slot.
_DEFAULT_APPLY_KEY = ""

# Per-node slots: HA replicas are separate hosts and may apply in parallel, while
# two applies on one host race for config/, result/ and iptables. RLock because
# the same task nests applies (task doall → HA file replicate → replica doall).
_APPLY_LOCKS: dict[str, threading.RLock] = {}
_APPLY_HELD: dict[str, int] = {}
_APPLY_GUARD = threading.Lock()

# Per-step progress; the task runner owns 0 and 100.
_STEP_PROGRESS: dict[str, tuple[int, str]] = {
    "sync": (5, "Синхронизация провайдеров…"),
    "doall": (10, "AntiZapret: запуск doall.sh…"),
    "profiles": (65, "AntiZapret: пересоздание профилей клиентов…"),
    "multihome": (90, "AntiZapret: восстановление OpenVPN multihome…"),
}


def apply_key_for_adapter(adapter: Any) -> str:
    """Slot key of the node behind ``adapter`` (same host for the same node)."""
    base_url = getattr(adapter, "base_url", None)
    if isinstance(base_url, str) and base_url:
        return f"remote:{base_url}"
    service = getattr(adapter, "_service", None)
    base_path = getattr(service, "base_path", None)
    if isinstance(base_path, (str, Path)):
        return f"local:{base_path}"
    return _DEFAULT_APPLY_KEY


def _apply_lock(key: str) -> threading.RLock:
    with _APPLY_GUARD:
        lock = _APPLY_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _APPLY_LOCKS[key] = lock
        return lock


@contextmanager
def apply_slot(*, timeout: float = 0.0, node_key: str | None = None) -> Iterator[None]:
    """Hold the apply slot of one node for the duration of the block.

    ``timeout=0`` is non-blocking: a second apply raises 409 instead of queueing
    behind the first one. The slot is reentrant inside the same thread, so a
    task that nests an apply step (doall → profiles → HA replicate) keeps it.
    """
    key = node_key or _DEFAULT_APPLY_KEY
    lock = _apply_lock(key)
    acquired = lock.acquire(timeout=timeout) if timeout > 0 else lock.acquire(blocking=False)
    if not acquired:
        raise HTTPException(status_code=409, detail=APPLY_BUSY_MESSAGE)
    with _APPLY_GUARD:
        _APPLY_HELD[key] = _APPLY_HELD.get(key, 0) + 1
    try:
        yield
    finally:
        with _APPLY_GUARD:
            _APPLY_HELD[key] = max(0, _APPLY_HELD.get(key, 0) - 1)
        lock.release()


def is_apply_busy(node_key: str | None = None) -> bool:
    """True while an apply holds a slot (any node, or the given one)."""
    with _APPLY_GUARD:
        if node_key is None:
            return any(count > 0 for count in _APPLY_HELD.values())
        return _APPLY_HELD.get(node_key, 0) > 0


def _step_text(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "").strip()


def apply_routing_changes(
    adapter: Any,
    *,
    sync: bool = True,
    doall: bool = True,
    ips_only: bool = True,
    recreate_profiles: bool = False,
    hosts: list[str] | None = None,
    ensure_multihome: bool = False,
    run_config_queue: bool = False,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run the configured apply steps in a fixed order and report each step.

    Holds the node's apply slot for the whole pipeline: a second apply on the
    same node raises 409 before its first step starts.

    Result keys, present only for the steps that ran: ``sync`` (adapter payload),
    ``doall_output`` (doall text), ``profiles`` (client.sh 7 text),
    ``openvpn_multihome`` (adapter payload), ``config_queue`` (flag echoed for the
    task report; the queue itself is owned by ``config_apply_queue``).

    Errors propagate as-is: a failed doall aborts before profiles, a failed
    profiles step keeps the already applied doall (no rollback), and multihome is
    skipped in both cases.
    """
    result: dict[str, Any] = {}

    with apply_slot(node_key=apply_key_for_adapter(adapter)):
        if sync:
            if progress:
                progress(*_STEP_PROGRESS["sync"], None)
            result["sync"] = adapter.sync_cidr_providers()

        if doall:
            if progress:
                progress(*_STEP_PROGRESS["doall"], None)
            # ``ips_only`` skips the ~100 MB hosts download: CIDR routes never read those lists.
            result["doall_output"] = adapter.apply_config_changes(ips_only=ips_only)

        if recreate_profiles:
            if progress:
                progress(*_STEP_PROGRESS["profiles"], None)
            profiles = recreate_openvpn_profiles(adapter, hosts=hosts)
            if not profiles.success:
                raise RuntimeError(
                    profiles.errors[0] if profiles.errors else "Ошибка пересоздания профилей"
                )
            result["profiles"] = profiles.output

        if ensure_multihome and doall:
            if progress:
                progress(*_STEP_PROGRESS["multihome"], None)
            multihome = maybe_ensure_openvpn_multihome(
                adapter, enabled=True, restart_if_unchanged=False
            )
            if multihome is not None:
                result["openvpn_multihome"] = multihome

        if run_config_queue:
            result["config_queue"] = True

    return result


def format_apply_output(result: dict[str, Any]) -> str:
    """Step outputs as one log text, in step order (task ``output`` field)."""
    parts = [
        _step_text(result.get("sync")),
        _step_text(result.get("doall_output")),
        _step_text(result.get("profiles")),
        _step_text(result.get("openvpn_multihome")),
    ]
    return "\n".join(part for part in parts if part).strip()
