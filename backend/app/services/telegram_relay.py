"""Forward one Bot API call to api.telegram.org (runs on the node agent)."""

from __future__ import annotations

import re

import httpx

MAX_RELAY_BODY_BYTES = 50 * 1024 * 1024
_TIMEOUT = httpx.Timeout(180.0, connect=10.0)
_METHOD_RE = re.compile(r"^[A-Za-z]{1,64}$")
_TOKEN_RE = re.compile(r"^\d{1,20}:[A-Za-z0-9_-]{20,100}$")
_transport: httpx.BaseTransport | None = None


class TelegramRelayInputError(ValueError):
    pass


class TelegramUnreachableError(RuntimeError):
    pass


def relay_bot_api_call(token: str, method: str, body: bytes, content_type: str) -> dict:
    if not _METHOD_RE.fullmatch(method) or not _TOKEN_RE.fullmatch(token):
        raise TelegramRelayInputError("Некорректный метод или токен бота")
    if len(body) > MAX_RELAY_BODY_BYTES:
        raise TelegramRelayInputError("Тело запроса больше 50 МБ")
    try:
        with httpx.Client(timeout=_TIMEOUT, transport=_transport) as client:
            response = client.post(
                f"https://api.telegram.org/bot{token}/{method}",
                content=body,
                headers={"Content-Type": content_type},
            )
    except httpx.RequestError as exc:
        # str(exc) may carry the request URL, and with it the bot token.
        raise TelegramUnreachableError(f"api.telegram.org недоступен с узла: {type(exc).__name__}") from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {"ok": False, "description": f"HTTP {response.status_code} от api.telegram.org"}
    return {"status": response.status_code, "body": payload}
