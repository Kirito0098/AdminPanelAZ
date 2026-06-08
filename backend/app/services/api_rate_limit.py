"""Global API rate limiting service (memory or Redis backend)."""

from __future__ import annotations

from app.config import get_settings
from app.services.rate_limit.backends import create_rate_limit_backend
from app.services.rate_limit.sliding_window import SlidingWindowLimiter

_API_DETAIL = "Слишком много запросов. Повторите позже."


class ApiRateLimitService:
    def __init__(self) -> None:
        self._limiter: SlidingWindowLimiter | None = None

    def _get_limiter(self) -> SlidingWindowLimiter:
        if self._limiter is None:
            settings = get_settings()
            backend = create_rate_limit_backend(
                backend=settings.api_rate_limit_backend,
                redis_url=settings.redis_url,
                prefix="api_rate:",
                label="API",
            )
            self._limiter = SlidingWindowLimiter(backend)
        return self._limiter

    def consume(self, client_ip: str) -> None:
        settings = get_settings()
        if not settings.api_rate_limit_enabled:
            return
        window = float(settings.api_rate_limit_window_seconds)
        max_requests = int(settings.api_rate_limit_max_requests)
        self._get_limiter().consume(client_ip, max_requests, window, detail=_API_DETAIL)


api_rate_limit_service = ApiRateLimitService()
