"""Rate limiting for authentication endpoints (memory or Redis backend)."""

from __future__ import annotations

from app.config import get_settings
from app.services.rate_limit.sliding_window import LazyRateLimiter

_AUTH_DETAIL = "Слишком много попыток входа. Повторите позже."


class AuthRateLimitService(LazyRateLimiter):
    _prefix = "auth_rate:"
    _label = "Auth"
    _backend_setting = "auth_rate_limit_backend"

    def check(self, client_ip: str, *, detail: str = _AUTH_DETAIL) -> None:
        settings = get_settings()
        if not settings.auth_rate_limit_enabled:
            return
        window = float(settings.auth_rate_limit_window_seconds)
        max_attempts = int(settings.auth_rate_limit_max_attempts)
        self._get_limiter().check(client_ip, max_attempts, window, detail=detail)

    def record_failure(self, client_ip: str) -> None:
        settings = get_settings()
        if not settings.auth_rate_limit_enabled:
            return
        window = float(settings.auth_rate_limit_window_seconds)
        self._get_limiter().record(client_ip, window)

    def record_success(self, client_ip: str) -> None:
        self._get_limiter().clear(client_ip)


auth_rate_limit_service = AuthRateLimitService()
