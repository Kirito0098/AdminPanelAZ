"""Cross-request TTL cache for remote node monitoring overview."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Callable

_lock = Lock()
_overview_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def monitoring_overview_cache_key(host: str, port: int) -> str:
    return f"{host}:{port}"


def get_cached_monitoring_overview(
    cache_key: str,
    ttl_seconds: int,
    fetcher: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    ttl = max(0, int(ttl_seconds))
    now = time.monotonic()
    if ttl > 0:
        with _lock:
            entry = _overview_cache.get(cache_key)
            if entry is not None and now < entry[0]:
                return entry[1]

    overview = fetcher()
    if ttl > 0:
        with _lock:
            _overview_cache[cache_key] = (now + ttl, overview)
    return overview


def invalidate_monitoring_overview(cache_key: str) -> None:
    with _lock:
        _overview_cache.pop(cache_key, None)
