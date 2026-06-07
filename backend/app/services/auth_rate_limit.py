"""Rate limiting for authentication endpoints (memory or Redis backend)."""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict

from fastapi import HTTPException, status

from app.config import get_settings

logger = logging.getLogger(__name__)


class RateLimitBackend(ABC):
    @abstractmethod
    def check(self, client_ip: str, max_attempts: int, window: float) -> None: ...

    @abstractmethod
    def record_failure(self, client_ip: str, window: float) -> None: ...

    @abstractmethod
    def record_success(self, client_ip: str) -> None: ...


class MemoryRateLimitBackend(RateLimitBackend):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def _prune(self, ip: str, window: float, now: float) -> list[float]:
        attempts = self._attempts.get(ip, [])
        fresh = [ts for ts in attempts if now - ts <= window]
        self._attempts[ip] = fresh
        return fresh

    def check(self, client_ip: str, max_attempts: int, window: float) -> None:
        now = time.time()
        with self._lock:
            attempts = self._prune(client_ip, window, now)
            if len(attempts) >= max_attempts:
                self._raise_limit(window)

    def record_failure(self, client_ip: str, window: float) -> None:
        now = time.time()
        with self._lock:
            self._prune(client_ip, window, now)
            self._attempts[client_ip].append(now)

    def record_success(self, client_ip: str) -> None:
        with self._lock:
            self._attempts.pop(client_ip, None)

    @staticmethod
    def _raise_limit(window: float) -> None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа. Повторите позже.",
            headers={"Retry-After": str(int(window))},
        )


class RedisRateLimitBackend(RateLimitBackend):
    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.from_url(redis_url, decode_responses=True)
        self._prefix = "auth_rate:"

    def _key(self, client_ip: str) -> str:
        return f"{self._prefix}{client_ip}"

    def check(self, client_ip: str, max_attempts: int, window: float) -> None:
        key = self._key(client_ip)
        count = self._client.zcount(key, time.time() - window, "+inf")
        if count >= max_attempts:
            MemoryRateLimitBackend._raise_limit(window)

    def record_failure(self, client_ip: str, window: float) -> None:
        key = self._key(client_ip)
        now = time.time()
        pipe = self._client.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.expire(key, int(window) + 1)
        pipe.execute()

    def record_success(self, client_ip: str) -> None:
        self._client.delete(self._key(client_ip))


def _create_backend() -> RateLimitBackend:
    settings = get_settings()
    if settings.auth_rate_limit_backend == "redis" and settings.redis_url:
        try:
            backend = RedisRateLimitBackend(settings.redis_url)
            backend._client.ping()
            logger.info("Auth rate limit: Redis backend enabled")
            return backend
        except Exception as exc:
            logger.warning("Redis rate limit unavailable, falling back to memory: %s", exc)
    return MemoryRateLimitBackend()


class AuthRateLimitService:
    def __init__(self) -> None:
        self._backend: RateLimitBackend | None = None

    def _get_backend(self) -> RateLimitBackend:
        if self._backend is None:
            self._backend = _create_backend()
        return self._backend

    def check(self, client_ip: str) -> None:
        settings = get_settings()
        if not settings.auth_rate_limit_enabled:
            return
        window = float(settings.auth_rate_limit_window_seconds)
        max_attempts = int(settings.auth_rate_limit_max_attempts)
        self._get_backend().check(client_ip, max_attempts, window)

    def record_failure(self, client_ip: str) -> None:
        settings = get_settings()
        if not settings.auth_rate_limit_enabled:
            return
        window = float(settings.auth_rate_limit_window_seconds)
        self._get_backend().record_failure(client_ip, window)

    def record_success(self, client_ip: str) -> None:
        self._get_backend().record_success(client_ip)


auth_rate_limit_service = AuthRateLimitService()
