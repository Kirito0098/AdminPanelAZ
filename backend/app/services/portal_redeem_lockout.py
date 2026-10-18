"""Per-portal-token lockout for unlock-code redeem (5 failures / 10 minutes)."""

from __future__ import annotations

from app.config import get_settings
from app.services.rate_limit.backends import create_rate_limit_backend
from app.services.rate_limit.sliding_window import SlidingWindowLimiter

_DETAIL = "Слишком много неверных попыток ввода ключа. Повторите через несколько минут."
_MAX_FAILURES = 5
_WINDOW_SECONDS = 600.0


class PortalRedeemLockoutService:
    def __init__(self) -> None:
        self._limiter: SlidingWindowLimiter | None = None

    def _get_limiter(self) -> SlidingWindowLimiter:
        if self._limiter is None:
            settings = get_settings()
            backend = create_rate_limit_backend(
                backend=settings.api_rate_limit_backend,
                redis_url=settings.redis_url,
                prefix="portal_redeem:",
                label="Portal redeem",
            )
            self._limiter = SlidingWindowLimiter(backend)
        return self._limiter

    def check(self, portal_token: str) -> None:
        self._get_limiter().check(
            portal_token,
            _MAX_FAILURES,
            _WINDOW_SECONDS,
            detail=_DETAIL,
        )

    def record_failure(self, portal_token: str) -> None:
        self._get_limiter().record(portal_token, _WINDOW_SECONDS)

    def record_success(self, portal_token: str) -> None:
        self._get_limiter().clear(portal_token)


portal_redeem_lockout_service = PortalRedeemLockoutService()
