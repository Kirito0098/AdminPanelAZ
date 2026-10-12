"""One path to the Telegram Bot API: direct, or through the node chosen in settings."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from app.services import telegram_api

RELAY_NODE_SETTING = "telegram_relay_node_id"


class TelegramRelayError(RuntimeError):
    pass


def relay_node_ineligible_reason(node) -> str | None:
    from app.services.node_transport import TRANSPORT_SSH, resolve_transport_id

    if node.is_local:
        return "Нужен удалённый узел: этот сервер и есть панель"
    if (node.node_kind or "vpn") != "vpn":
        return "Прокси-узел стоит в РФ и не поможет достучаться до Telegram"
    if not node.mtls_enabled and resolve_transport_id(node) != TRANSPORT_SSH:
        return "Канал до узла не шифруется: включите mTLS или SSH-транспорт на странице «Узлы»"
    return None


def current_relay_setting() -> str:
    """Id of the relay node as stored, or "" when Telegram is reached directly."""
    from app.database import SessionLocal
    from app.services.app_setting_store import _get_setting

    with SessionLocal() as db:
        return _get_setting(db, RELAY_NODE_SETTING).strip()


def _relay_adapter():
    """Adapter of the relay node, or None when Telegram is reached directly."""
    from app.database import SessionLocal
    from app.models import Node
    from app.services.app_setting_store import _get_setting
    from app.services.node_manager import get_adapter_for_node

    with SessionLocal() as db:
        raw = _get_setting(db, RELAY_NODE_SETTING).strip()
        if not raw:
            return None
        node = db.get(Node, int(raw))
        if node is None:
            raise TelegramRelayError("Узел для связи с Telegram удалён — выберите другой в настройках Telegram")
        reason = relay_node_ineligible_reason(node)
        if reason:
            raise TelegramRelayError(f"Узел «{node.name}»: {reason}")
        adapter = get_adapter_for_node(node)
        adapter.node_name = node.name
        return adapter


def _encode(
    token: str,
    method: str,
    *,
    json: Any = None,
    data: Any = None,
    files: Any = None,
    timeout: httpx.Timeout | float | None = None,
) -> httpx.Request:
    if json is None and not data and not files:
        json = {}
    request = httpx.Request(
        "POST",
        telegram_api.bot_api_url(token, method),
        json=json,
        data=data,
        files=files,
        extensions={"timeout": httpx.Timeout(timeout if timeout is not None else telegram_api._TIMEOUT).as_dict()},
    )
    request.read()
    return request


def _relay_envelope(adapter, call: Callable[[Any], dict]) -> dict:
    try:
        return call(adapter)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise TelegramRelayError(
                f"Агент узла «{adapter.node_name}» не умеет пересылать запросы Telegram — обновите агент до 1.13.0"
            ) from exc
        detail = exc.detail.get("message") if isinstance(exc.detail, dict) else exc.detail
        raise TelegramRelayError(f"Узел «{adapter.node_name}»: {detail}") from exc
    finally:
        adapter.close()


def _via_relay(adapter, token: str, method: str, request: httpx.Request) -> dict:
    envelope = _relay_envelope(
        adapter, lambda a: a.telegram_bot_api(token, method, request.content, request.headers["content-type"])
    )
    return envelope["body"]


def bot_api_post_sync(
    token: str,
    method: str,
    *,
    json: Any = None,
    data: Any = None,
    files: Any = None,
    timeout: httpx.Timeout | float | None = None,
) -> dict:
    request = _encode(token, method, json=json, data=data, files=files, timeout=timeout)
    adapter = _relay_adapter()
    if adapter is not None:
        return _via_relay(adapter, token, method, request)
    return telegram_api._get_bot_api_sync_client().send(request).json()


async def bot_api_post(
    token: str,
    method: str,
    *,
    json: Any = None,
    timeout: httpx.Timeout | float | None = None,
) -> dict:
    request = _encode(token, method, json=json, timeout=timeout)
    adapter = await asyncio.to_thread(_relay_adapter)
    if adapter is not None:
        return await asyncio.to_thread(_via_relay, adapter, token, method, request)
    response = await telegram_api._get_bot_api_client().send(request)
    return response.json()


def _json_or_text(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"error": response.text.strip() or response.reason_phrase}


def oidc_token_exchange_sync(form: dict[str, str], *, client_id: str, client_secret: str) -> tuple[int, Any]:
    """POST the OIDC token form to oauth.telegram.org; returns (HTTP status, parsed body)."""
    from app.services.telegram_relay import OIDC_TOKEN_URL

    adapter = _relay_adapter()
    if adapter is not None:
        body = urlencode(form).encode()
        authorization = "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        envelope = _relay_envelope(adapter, lambda a: a.telegram_oidc_token(body, authorization))
        return envelope["status"], envelope["body"]
    response = httpx.post(OIDC_TOKEN_URL, data=form, auth=(client_id, client_secret), timeout=15.0)
    return response.status_code, _json_or_text(response)


def oidc_jwks_sync() -> dict:
    from app.services.telegram_relay import OIDC_JWKS_URL

    adapter = _relay_adapter()
    if adapter is not None:
        envelope = _relay_envelope(adapter, lambda a: a.telegram_oidc_jwks())
        if envelope["status"] >= 400:
            raise TelegramRelayError(f"oauth.telegram.org вернул HTTP {envelope['status']} на запрос ключей")
        return envelope["body"]
    response = httpx.get(OIDC_JWKS_URL, timeout=10.0)
    response.raise_for_status()
    return response.json()
