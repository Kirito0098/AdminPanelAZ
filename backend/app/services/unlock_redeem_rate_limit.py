"""Rate limit unlock-code redeem attempts per telegram_id (5 / 600s)."""

from __future__ import annotations

from app.services.rate_limit.backends import MemoryRateLimitBackend
from app.services.rate_limit.sliding_window import RateLimitExceeded, SlidingWindowLimiter

_DETAIL = "Слишком много попыток. Подождите 10 минут."


class UnlockRedeemRateLimitService:
    def __init__(self) -> None:
        self._limiter = SlidingWindowLimiter(MemoryRateLimitBackend())

    def consume(self, telegram_id: str) -> str | None:
        try:
            self._limiter.consume(f"unlock-redeem:{telegram_id}", 5, 600.0, detail=_DETAIL)
        except RateLimitExceeded:
            return _DETAIL
        return None


unlock_redeem_rate_limit_service = UnlockRedeemRateLimitService()
