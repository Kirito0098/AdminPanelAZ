"""Sliding-window rate limit backends (memory or Redis)."""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimitBackend(ABC):
    @abstractmethod
    def count(self, key: str, window: float) -> int: ...

    @abstractmethod
    def add(self, key: str, window: float) -> None: ...

    @abstractmethod
    def clear(self, key: str) -> None: ...


class MemoryRateLimitBackend(RateLimitBackend):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, list[float]] = defaultdict(list)

    def _prune(self, key: str, window: float, now: float) -> list[float]:
        events = self._events.get(key, [])
        fresh = [ts for ts in events if now - ts <= window]
        self._events[key] = fresh
        return fresh

    def count(self, key: str, window: float) -> int:
        now = time.time()
        with self._lock:
            return len(self._prune(key, window, now))

    def add(self, key: str, window: float) -> None:
        now = time.time()
        with self._lock:
            self._prune(key, window, now)
            self._events[key].append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


class RedisRateLimitBackend(RateLimitBackend):
    def __init__(self, redis_url: str, prefix: str) -> None:
        import redis

        self._client = redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def count(self, key: str, window: float) -> int:
        return int(self._client.zcount(self._key(key), time.time() - window, "+inf"))

    def add(self, key: str, window: float) -> None:
        redis_key = self._key(key)
        now = time.time()
        pipe = self._client.pipeline()
        pipe.zadd(redis_key, {str(now): now})
        pipe.zremrangebyscore(redis_key, 0, now - window)
        pipe.expire(redis_key, int(window) + 1)
        pipe.execute()

    def clear(self, key: str) -> None:
        self._client.delete(self._key(key))


def create_rate_limit_backend(
    *,
    backend: str,
    redis_url: str,
    prefix: str,
    label: str,
) -> RateLimitBackend:
    if backend == "redis" and redis_url:
        try:
            instance = RedisRateLimitBackend(redis_url, prefix)
            instance._client.ping()
            logger.info("%s rate limit: Redis backend enabled", label)
            return instance
        except Exception as exc:
            logger.warning("%s rate limit: Redis unavailable, falling back to memory: %s", label, exc)
    return MemoryRateLimitBackend()
