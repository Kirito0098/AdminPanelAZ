"""Rate limiting for authentication endpoints (memory or Redis backend)."""

from __future__ import annotations

from app.config import get_settings
from app.services.rate_limit.backends import create_rate_limit_backend
from app.services.rate_limit.sliding_window import SlidingWindowLimiter

_AUTH_DETAIL = "Слишком много попыток входа. Повторите позже."


class AuthRateLimitService:
    def __init__(self) -> None:
        self._limiter: SlidingWindowLimiter | None = None

    def _get_limiter(self) -> SlidingWindowLimiter:
        if self._limiter is None:
            settings = get_settings()
            backend = create_rate_limit_backend(
                backend=settings.auth_rate_limit_backend,
                redis_url=settings.redis_url,
                prefix="auth_rate:",
                label="Auth",
            )
            self._limiter = SlidingWindowLimiter(backend)
        return self._limiter

    def check(self, client_ip: str) -> None:
        settings = get_settings()
        if not settings.auth_rate_limit_enabled:
            return
        window = float(settings.auth_rate_limit_window_seconds)
        max_attempts = int(settings.auth_rate_limit_max_attempts)
        self._get_limiter().check(client_ip, max_attempts, window, detail=_AUTH_DETAIL)

    def record_failure(self, client_ip: str) -> None:
        settings = get_settings()
        if not settings.auth_rate_limit_enabled:
            return
        window = float(settings.auth_rate_limit_window_seconds)
        self._get_limiter().record(client_ip, window)

    def record_success(self, client_ip: str) -> None:
        self._get_limiter().clear(client_ip)


auth_rate_limit_service = AuthRateLimitService()
