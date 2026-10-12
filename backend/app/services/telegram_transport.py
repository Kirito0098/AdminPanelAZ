"""One path to the Telegram Bot API: direct, or through the node chosen in settings."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import HTTPException

from app.services import telegram_api

RELAY_NODE_SETTING = "telegram_relay_node_id"


class TelegramRelayError(RuntimeError):
    pass


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


def _via_relay(adapter, token: str, method: str, request: httpx.Request) -> dict:
    try:
        envelope = adapter.telegram_bot_api(token, method, request.content, request.headers["content-type"])
    except HTTPException as exc:
        if exc.status_code == 404:
            raise TelegramRelayError(
                f"Агент узла «{adapter.node_name}» не умеет пересылать запросы Telegram — обновите агент до 1.13.0"
            ) from exc
        detail = exc.detail.get("message") if isinstance(exc.detail, dict) else exc.detail
        raise TelegramRelayError(f"Узел «{adapter.node_name}»: {detail}") from exc
    finally:
        adapter.close()
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
