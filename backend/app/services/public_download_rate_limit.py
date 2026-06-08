"""Stricter rate limit for public route-file downloads (AA parity: 30/min)."""

from __future__ import annotations

from app.config import get_settings
from app.services.rate_limit.backends import create_rate_limit_backend
from app.services.rate_limit.sliding_window import SlidingWindowLimiter

_PUBLIC_DL_DETAIL = "Слишком много запросов на скачивание. Повторите позже."
_PUBLIC_DL_LIMIT = 30
_PUBLIC_DL_WINDOW = 60.0


class PublicDownloadRateLimitService:
    def __init__(self) -> None:
        self._limiter: SlidingWindowLimiter | None = None

    def _get_limiter(self) -> SlidingWindowLimiter:
        if self._limiter is None:
            settings = get_settings()
            backend = create_rate_limit_backend(
                backend=settings.api_rate_limit_backend,
                redis_url=settings.redis_url,
                prefix="public_dl:",
                label="Public download",
            )
            self._limiter = SlidingWindowLimiter(backend)
        return self._limiter

    def consume(self, client_ip: str) -> None:
        if not get_settings().api_rate_limit_enabled:
            return
        self._get_limiter().consume(
            client_ip,
            _PUBLIC_DL_LIMIT,
            _PUBLIC_DL_WINDOW,
            detail=_PUBLIC_DL_DETAIL,
        )


public_download_rate_limit_service = PublicDownloadRateLimitService()
