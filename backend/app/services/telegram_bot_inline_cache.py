"""TTL cache for Telegram inline query results."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Callable

_lock = Lock()
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

INLINE_RESULTS_TTL_SECONDS = 60


def inline_results_cache_key(telegram_user_id: str, query: str) -> str:
    normalized = (query or "").strip().lower()
    return f"{telegram_user_id}:{normalized}"


def get_cached_inline_results(
    cache_key: str,
    ttl_seconds: int,
    fetcher: Callable[[], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    ttl = max(0, int(ttl_seconds))
    now = time.monotonic()
    if ttl > 0:
        with _lock:
            entry = _cache.get(cache_key)
            if entry is not None and now < entry[0]:
                return entry[1]

    results = fetcher()
    if ttl > 0:
        with _lock:
            _cache[cache_key] = (now + ttl, results)
    return results


def invalidate_inline_results(cache_key: str) -> None:
    with _lock:
        _cache.pop(cache_key, None)


def clear_inline_results_cache() -> None:
    with _lock:
        _cache.clear()
