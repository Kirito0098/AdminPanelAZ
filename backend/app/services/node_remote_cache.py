"""Cross-request TTL cache for remote node monitoring overview."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_lock = Lock()
_overview_cache: dict[str, tuple[float, Any]] = {}


def monitoring_overview_cache_key(host: str, port: int) -> str:
    return f"{host}:{port}"


FEDERATED_OVERVIEW_CACHE_KEY = "federated:overview:all"
GLOBAL_DASHBOARD_CACHE_KEY = "federated:global-summary"
NODES_COMPARE_CACHE_KEY = "federated:nodes-compare"


def get_cached_monitoring_overview(
    cache_key: str,
    ttl_seconds: int,
    fetcher: Callable[[], T],
) -> tuple[T, bool]:
    """Return (value, served_from_cache)."""
    ttl = max(0, int(ttl_seconds))
    now = time.monotonic()
    if ttl > 0:
        with _lock:
            entry = _overview_cache.get(cache_key)
            if entry is not None and now < entry[0]:
                return entry[1], True

    overview = fetcher()
    if ttl > 0:
        with _lock:
            _overview_cache[cache_key] = (now + ttl, overview)
    return overview, False


def invalidate_monitoring_overview(cache_key: str) -> None:
    with _lock:
        _overview_cache.pop(cache_key, None)
