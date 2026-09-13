"""Refresh-token cookie Secure flag helpers."""

from __future__ import annotations

from fastapi import Request

from app.config import Settings


def client_request_is_https(request: Request | None) -> bool | None:
    """Whether the browser-facing request used HTTPS.

    Returns ``None`` when ``request`` is missing. Prefers ``X-Forwarded-Proto``
    (first hop) when present so TLS-terminated proxies still count as HTTPS.
    """
    if request is None:
        return None
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    scheme = forwarded or (request.url.scheme or "").strip().lower()
    if scheme == "https":
        return True
    if scheme == "http":
        return False
    return None


def refresh_token_cookie_secure(settings: Settings, request: Request | None = None) -> bool:
    """Decide Secure for the refresh cookie.

    On plain HTTP the browser ignores Secure cookies, so login appears to work
    (access JWT in memory) until the first refresh — often on tab focus.
    Never force Secure solely because ``APP_ENV=production``.
    """
    https = client_request_is_https(request)
    if https is False:
        return False
    if https is True:
        return True
    # No request context (or unknown scheme): settings / deployment hints only.
    return bool(
        settings.refresh_token_cookie_secure
        or settings.enforce_https
        or settings.behind_nginx
    )
