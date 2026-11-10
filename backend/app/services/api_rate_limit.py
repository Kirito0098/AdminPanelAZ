"""Global API rate limiting service (memory or Redis backend)."""

from __future__ import annotations

from app.config import get_settings
from app.services.rate_limit.sliding_window import LazyRateLimiter

_API_DETAIL = "Слишком много запросов. Повторите позже."


class ApiRateLimitService(LazyRateLimiter):
    _prefix = "api_rate:"
    _label = "API"

    def consume(self, client_ip: str) -> None:
        settings = get_settings()
        if not settings.api_rate_limit_enabled:
            return
        window = float(settings.api_rate_limit_window_seconds)
        max_requests = int(settings.api_rate_limit_max_requests)
        self._get_limiter().consume(client_ip, max_requests, window, detail=_API_DETAIL)


api_rate_limit_service = ApiRateLimitService()
