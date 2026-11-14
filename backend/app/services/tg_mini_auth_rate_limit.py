"""Stricter rate limit for Mini App sign-in (20 attempts / 60 s per IP).

In-memory like the neighbouring per-surface limiters: the counter lives in the
worker process, so on a multi-worker install the limit is enforced per worker,
not globally. That is acceptable here — the goal is to stop a single caller
from driving admin notifications, not to build a distributed quota.
"""

from __future__ import annotations

from app.services.rate_limit.backends import MemoryRateLimitBackend
from app.services.rate_limit.sliding_window import SlidingWindowLimiter

_TG_MINI_AUTH_DETAIL = "Слишком много попыток входа. Повторите позже."
_TG_MINI_AUTH_LIMIT = 20
_TG_MINI_AUTH_WINDOW = 60.0


class TgMiniAuthRateLimitService:
    def __init__(self) -> None:
        self._limiter = SlidingWindowLimiter(MemoryRateLimitBackend())

    def consume(self, client_ip: str) -> None:
        self._limiter.consume(
            f"tg-mini-auth:{client_ip}",
            _TG_MINI_AUTH_LIMIT,
            _TG_MINI_AUTH_WINDOW,
            detail=_TG_MINI_AUTH_DETAIL,
        )


tg_mini_auth_rate_limit_service = TgMiniAuthRateLimitService()
