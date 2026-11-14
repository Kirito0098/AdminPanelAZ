"""Per-portal-token lockout for unlock-code redeem (5 failures / 10 minutes)."""

from __future__ import annotations

from app.config import get_settings
from app.services.rate_limit.sliding_window import LazyRateLimiter

_DETAIL = "Слишком много неверных попыток ввода ключа. Повторите через несколько минут."
_MAX_FAILURES = 5
_WINDOW_SECONDS = 600.0


class PortalRedeemLockoutService(LazyRateLimiter):
    _prefix = "portal_redeem:"
    _label = "Portal redeem"

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
