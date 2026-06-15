"""Async Telegram Bot API client for interactive bot replies."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


async def call_bot_api(
    bot_token: str,
    method: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not bot_token:
        return None
    url = _API_BASE.format(token=bot_token, method=method)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(url, json=payload or {})
            data = response.json()
            if not data.get("ok"):
                logger.warning("Telegram API %s failed: %s", method, data.get("description"))
                return None
            return data.get("result")
    except Exception as exc:
        logger.warning("Telegram API %s error: %s", method, exc)
        return None


async def send_message(
    bot_token: str,
    chat_id: str | int,
    text: str,
    *,
    parse_mode: str = "HTML",
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return (await call_bot_api(bot_token, "sendMessage", payload=payload)) is not None


async def edit_message_text(
    bot_token: str,
    chat_id: str | int,
    message_id: int,
    text: str,
    *,
    parse_mode: str = "HTML",
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return (await call_bot_api(bot_token, "editMessageText", payload=payload)) is not None


async def answer_callback_query(
    bot_token: str,
    callback_query_id: str,
    *,
    text: str | None = None,
    show_alert: bool = False,
) -> bool:
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    return (await call_bot_api(bot_token, "answerCallbackQuery", payload=payload)) is not None


async def set_webhook(bot_token: str, url: str, *, secret_token: str | None = None) -> tuple[bool, str]:
    payload: dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    }
    if secret_token:
        payload["secret_token"] = secret_token
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                _API_BASE.format(token=bot_token, method="setWebhook"),
                json=payload,
            )
            data = response.json()
            if data.get("ok"):
                return True, ""
            return False, str(data.get("description") or "setWebhook failed")
    except Exception as exc:
        return False, str(exc)


async def delete_webhook(bot_token: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                _API_BASE.format(token=bot_token, method="deleteWebhook"),
                json={"drop_pending_updates": True},
            )
            data = response.json()
            if data.get("ok"):
                return True, ""
            return False, str(data.get("description") or "deleteWebhook failed")
    except Exception as exc:
        return False, str(exc)


def delete_webhook_sync(bot_token: str) -> tuple[bool, str]:
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.post(
                _API_BASE.format(token=bot_token, method="deleteWebhook"),
                json={"drop_pending_updates": True},
            )
            data = response.json()
            if data.get("ok"):
                return True, ""
            return False, str(data.get("description") or "deleteWebhook failed")
    except Exception as exc:
        return False, str(exc)


def set_webhook_sync(bot_token: str, url: str, *, secret_token: str | None = None) -> tuple[bool, str]:
    payload: dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    }
    if secret_token:
        payload["secret_token"] = secret_token
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.post(
                _API_BASE.format(token=bot_token, method="setWebhook"),
                json=payload,
            )
            data = response.json()
            if data.get("ok"):
                return True, ""
            return False, str(data.get("description") or "setWebhook failed")
    except Exception as exc:
        return False, str(exc)


async def get_webhook_info(bot_token: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                _API_BASE.format(token=bot_token, method="getWebhookInfo"),
            )
            data = response.json()
            if data.get("ok"):
                return data.get("result") or {}
    except Exception as exc:
        logger.warning("getWebhookInfo error: %s", exc)
    return {}


async def set_my_commands(bot_token: str, commands: list[dict[str, str]]) -> bool:
    payload = {"commands": commands}
    return (await call_bot_api(bot_token, "setMyCommands", payload=payload)) is not None


def set_my_commands_sync(bot_token: str, commands: list[dict[str, str]]) -> tuple[bool, str]:
    payload = {"commands": commands}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.post(
                _API_BASE.format(token=bot_token, method="setMyCommands"),
                json=payload,
            )
            data = response.json()
            if data.get("ok"):
                return True, ""
            return False, str(data.get("description") or "setMyCommands failed")
    except Exception as exc:
        return False, str(exc)
