"""Forward Telegram calls to fixed telegram.org endpoints (runs on the node agent)."""

from __future__ import annotations

import re

import httpx

MAX_RELAY_BODY_BYTES = 50 * 1024 * 1024
MAX_OIDC_BODY_BYTES = 16 * 1024
OIDC_TOKEN_URL = "https://oauth.telegram.org/token"
OIDC_JWKS_URL = "https://oauth.telegram.org/.well-known/jwks.json"
_TIMEOUT = httpx.Timeout(180.0, connect=10.0)
_METHOD_RE = re.compile(r"^[A-Za-z]{1,64}$")
_TOKEN_RE = re.compile(r"^\d{1,20}:[A-Za-z0-9_-]{20,100}$")
_transport: httpx.BaseTransport | None = None


class TelegramRelayInputError(ValueError):
    pass


class TelegramUnreachableError(RuntimeError):
    pass


def _send(method: str, url: str, *, body: bytes | None = None, headers: dict[str, str] | None = None) -> dict:
    host = httpx.URL(url).host
    try:
        with httpx.Client(timeout=_TIMEOUT, transport=_transport) as client:
            response = client.request(method, url, content=body, headers=headers)
    except httpx.RequestError as exc:
        # str(exc) may carry the request URL, and with it the bot token.
        raise TelegramUnreachableError(f"{host} недоступен с узла: {type(exc).__name__}") from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {"ok": False, "description": f"HTTP {response.status_code} от {host}"}
    return {"status": response.status_code, "body": payload}


def relay_bot_api_call(token: str, method: str, body: bytes, content_type: str) -> dict:
    if not _METHOD_RE.fullmatch(method) or not _TOKEN_RE.fullmatch(token):
        raise TelegramRelayInputError("Некорректный метод или токен бота")
    if len(body) > MAX_RELAY_BODY_BYTES:
        raise TelegramRelayInputError("Тело запроса больше 50 МБ")
    return _send(
        "POST",
        f"https://api.telegram.org/bot{token}/{method}",
        body=body,
        headers={"Content-Type": content_type},
    )


def relay_oidc_token(body: bytes, authorization: str) -> dict:
    if len(body) > MAX_OIDC_BODY_BYTES:
        raise TelegramRelayInputError("Тело запроса больше 16 КБ")
    return _send(
        "POST",
        OIDC_TOKEN_URL,
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Authorization": authorization},
    )


def relay_oidc_jwks() -> dict:
    return _send("GET", OIDC_JWKS_URL)
