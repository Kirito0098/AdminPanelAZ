"""Sliding-window rate limiter built on shared backends."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.config import get_settings
from app.services.rate_limit.backends import RateLimitBackend, create_rate_limit_backend


class RateLimitExceeded(HTTPException):
    def __init__(self, *, detail: str, window: float) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(int(window))},
        )


class SlidingWindowLimiter:
    def __init__(self, backend: RateLimitBackend) -> None:
        self._backend = backend

    def check(self, key: str, limit: int, window: float, *, detail: str) -> None:
        if self._backend.count(key, window) >= limit:
            raise RateLimitExceeded(detail=detail, window=window)

    def consume(self, key: str, limit: int, window: float, *, detail: str) -> None:
        self.check(key, limit, window, detail=detail)
        self._backend.add(key, window)

    def record(self, key: str, window: float) -> None:
        self._backend.add(key, window)

    def clear(self, key: str) -> None:
        self._backend.clear(key)


class LazyRateLimiter:
    """Builds its sliding-window limiter once, on first use."""

    _prefix = ""
    _label = ""
    _backend_setting = "api_rate_limit_backend"

    def __init__(self) -> None:
        self._limiter: SlidingWindowLimiter | None = None

    def _get_limiter(self) -> SlidingWindowLimiter:
        if self._limiter is None:
            settings = get_settings()
            self._limiter = SlidingWindowLimiter(
                create_rate_limit_backend(
                    backend=getattr(settings, self._backend_setting),
                    redis_url=settings.redis_url,
                    prefix=self._prefix,
                    label=self._label,
                )
            )
        return self._limiter

