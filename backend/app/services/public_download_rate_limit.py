"""Stricter rate limit for public route-file downloads (AA parity: 30/min)."""

from __future__ import annotations

from app.config import get_settings
from app.services.rate_limit.sliding_window import LazyRateLimiter

_PUBLIC_DL_DETAIL = "Слишком много запросов на скачивание. Повторите позже."
_PUBLIC_DL_LIMIT = 30
_PUBLIC_DL_WINDOW = 60.0


class PublicDownloadRateLimitService(LazyRateLimiter):
    _prefix = "public_dl:"
    _label = "Public download"

    def consume(self, client_ip: str) -> None:
        # Always on for public surfaces — independent of general API rate limiting.
        self._get_limiter().consume(
            client_ip,
            _PUBLIC_DL_LIMIT,
            _PUBLIC_DL_WINDOW,
            detail=_PUBLIC_DL_DETAIL,
        )


public_download_rate_limit_service = PublicDownloadRateLimitService()
