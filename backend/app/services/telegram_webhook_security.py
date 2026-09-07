"""Telegram webhook IP allowlist and rate limiting."""

from __future__ import annotations

import hmac
import ipaddress

from app.services.rate_limit.backends import MemoryRateLimitBackend
from app.services.rate_limit.sliding_window import SlidingWindowLimiter

# https://core.telegram.org/bots/webhooks#the-short-version
_TELEGRAM_CIDRS = (
    ipaddress.ip_network("149.154.160.0/20"),
    ipaddress.ip_network("91.108.4.0/22"),
)

# https://core.telegram.org/bots/api#setwebhook — secret_token header name
TELEGRAM_SECRET_TOKEN_HEADER = "X-Telegram-Bot-Api-Secret-Token"

_webhook_limiter = SlidingWindowLimiter(MemoryRateLimitBackend())
_WEBHOOK_MAX_REQUESTS = 30
_WEBHOOK_WINDOW_SECONDS = 1.0


def secrets_match(provided: str | None, expected: str | None) -> bool:
    """Constant-time compare for webhook URL/header secrets."""
    left = (provided or "").encode("utf-8")
    right = (expected or "").encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def get_telegram_webhook_client_ip(request) -> str:
    """Resolve client IP for webhook allowlist — never trust client X-Forwarded-For."""
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    return (request.client.host if request.client else "") or ""


def is_telegram_ip(client_ip: str) -> bool:
    if not client_ip:
        return False
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    return any(addr in network for network in _TELEGRAM_CIDRS)


def consume_webhook_rate_limit(client_ip: str) -> None:
    _webhook_limiter.consume(
        f"tg-webhook:{client_ip}",
        _WEBHOOK_MAX_REQUESTS,
        _WEBHOOK_WINDOW_SECONDS,
        detail="Webhook rate limit exceeded",
    )
