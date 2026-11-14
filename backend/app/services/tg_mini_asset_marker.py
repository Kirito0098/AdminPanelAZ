"""Signed cookie that lets a signed-in Mini App download its lazy chunks.

The Mini App entry bundle (shell, navigation, configs screen) loads before sign-in;
admin and extra screens are separate chunks. ``app/routers/tg_mini/static.py`` serves
those only to a browser holding this marker, so an anonymous visitor who downloads the
entry bundle still cannot read the admin screens out of it.

The marker is bound to the Telegram account that signed in and expires on its own:
the Mini App token lives 30 minutes, so a fresh ``/auth`` always renews the marker.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import Request, Response

from app.config import Settings
from app.services.auth_cookies import refresh_token_cookie_secure

TG_MINI_ASSET_COOKIE = "tg_mini_asset"
TG_MINI_ASSET_MAX_AGE = 12 * 3600


def _signature(secret_key: str, telegram_id: str, expires_at: int) -> str:
    key = hmac.new(secret_key.encode(), b"tg-mini-asset-marker", hashlib.sha256).digest()
    digest = hmac.new(key, f"{telegram_id}:{expires_at}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def issue_tg_mini_asset_marker(
    secret_key: str,
    telegram_id: str,
    *,
    max_age: int = TG_MINI_ASSET_MAX_AGE,
    now: float | None = None,
) -> str:
    expires_at = int(time.time() if now is None else now) + max_age
    return f"{telegram_id}.{expires_at}.{_signature(secret_key, telegram_id, expires_at)}"


def tg_mini_asset_marker_valid(secret_key: str, value: str | None, *, now: float | None = None) -> bool:
    parts = (value or "").split(".")
    if len(parts) != 3:
        return False
    telegram_id, expires_raw, signature = parts
    if not (telegram_id.isascii() and telegram_id.isdigit()) or not (expires_raw.isascii() and expires_raw.isdigit()):
        return False
    if not signature:
        return False
    expires_at = int(expires_raw)
    if expires_at <= (time.time() if now is None else now):
        return False
    return hmac.compare_digest(signature.encode(), _signature(secret_key, telegram_id, expires_at).encode())


def _cookie_options(settings: Settings, request: Request | None) -> dict:
    return {
        "path": "/",
        "httponly": True,
        "secure": refresh_token_cookie_secure(settings, request),
        "samesite": "lax",
    }


def set_tg_mini_asset_marker_cookie(
    response: Response,
    settings: Settings,
    telegram_id: str,
    request: Request | None = None,
) -> None:
    response.set_cookie(
        key=TG_MINI_ASSET_COOKIE,
        value=issue_tg_mini_asset_marker(settings.secret_key, telegram_id),
        max_age=TG_MINI_ASSET_MAX_AGE,
        **_cookie_options(settings, request),
    )
