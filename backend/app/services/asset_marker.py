"""Signed cookie that lets a signed-in browser download the login-only frontend chunks."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import Request, Response

from app.config import Settings
from app.services.auth_cookies import refresh_token_cookie_secure
from app.services.panel_paths import with_access_path

ASSET_MARKER_COOKIE = "asset_session"


def _signature(secret_key: str, expires_at: int) -> str:
    key = hmac.new(secret_key.encode(), b"asset-marker", hashlib.sha256).digest()
    digest = hmac.new(key, str(expires_at).encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def issue_asset_marker(secret_key: str, max_age: int, *, now: float | None = None) -> str:
    expires_at = int(time.time() if now is None else now) + max_age
    return f"{expires_at}.{_signature(secret_key, expires_at)}"


def asset_marker_valid(secret_key: str, value: str | None, *, now: float | None = None) -> bool:
    expires_raw, _, signature = (value or "").partition(".")
    if not (expires_raw.isascii() and expires_raw.isdigit()) or not signature:
        return False
    expires_at = int(expires_raw)
    if expires_at <= (time.time() if now is None else now):
        return False
    return hmac.compare_digest(signature.encode(), _signature(secret_key, expires_at).encode())


def _cookie_options(settings: Settings, request: Request | None) -> dict:
    return {
        "path": with_access_path(settings, "/assets"),
        "httponly": True,
        "secure": refresh_token_cookie_secure(settings, request),
        "samesite": "strict",
    }


def set_asset_marker_cookie(response: Response, settings: Settings, request: Request | None = None) -> None:
    max_age = settings.refresh_token_expire_days * 86400
    response.set_cookie(
        key=ASSET_MARKER_COOKIE,
        value=issue_asset_marker(settings.secret_key, max_age),
        max_age=max_age,
        **_cookie_options(settings, request),
    )


def clear_asset_marker_cookie(response: Response, settings: Settings, request: Request | None = None) -> None:
    response.delete_cookie(key=ASSET_MARKER_COOKIE, **_cookie_options(settings, request))
