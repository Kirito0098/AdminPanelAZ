"""Async Telegram Bot API client for interactive bot replies."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_TELEGRAM_API_HOST = "api.telegram.org"


def format_telegram_connect_error(message: str, *, operation: str) -> str:
    """Turn low-level httpx/socket errors into actionable Russian messages."""
    msg = (message or "").strip()
    lower = msg.lower()

    if "network is unreachable" in lower or "errno 101" in lower or "[errno 101]" in lower:
        return (
            f"Не удалось {operation}: сервер панели не может достучаться до {_TELEGRAM_API_HOST} "
            "(сеть недоступна). Панель отправляет исходящий запрос к Telegram API, чтобы "
            "зарегистрировать webhook — это не связано с HTTPS вашего сайта. "
            "Проверьте интернет на сервере, маршрутизацию, исходящий фаервол и не блокирует ли "
            "хостинг Telegram. На сервере выполните: curl -4 https://api.telegram.org/. "
            f"Технически: {msg}"
        )

    if "connection refused" in lower or "errno 111" in lower or "[errno 111]" in lower:
        return (
            f"Не удалось {operation}: соединение с {_TELEGRAM_API_HOST} отклонено. "
            "Проверьте исходящий доступ сервера к интернету и правила фаервола. "
            f"Технически: {msg}"
        )

    if (
        "timed out" in lower
        or "timeout" in lower
        or "errno 110" in lower
        or "[errno 110]" in lower
    ):
        return (
            f"Не удалось {operation}: истекло время ожидания ответа от {_TELEGRAM_API_HOST}. "
            "Проверьте стабильность интернета на сервере и повторите попытку. "
            f"Технически: {msg}"
        )

    if (
        "name or service not known" in lower
        or "nodename nor servname provided" in lower
        or "getaddrinfo" in lower
        or "errno -2" in lower
        or "errno -3" in lower
    ):
        return (
            f"Не удалось {operation}: сервер не может разрешить DNS-имя {_TELEGRAM_API_HOST}. "
            "Проверьте DNS на сервере (/etc/resolv.conf) и доступность резолвера. "
            f"Технически: {msg}"
        )

    if "certificate verify failed" in lower or ("ssl" in lower and "error" in lower):
        return (
            f"Не удалось {operation}: ошибка TLS при подключении к {_TELEGRAM_API_HOST}. "
            "Проверьте системное время на сервере и корневые сертификаты CA. "
            f"Технически: {msg}"
        )

    if "https url must be provided" in lower:
        return (
            f"Не удалось {operation}: Telegram принимает webhook только по HTTPS. "
            "Укажите в настройках панели публичный адрес с https:// и доступным сертификатом. "
            f"Технически: {msg}"
        )

    if msg:
        return f"Не удалось {operation}: {msg}"

    return f"Не удалось {operation}: неизвестная ошибка соединения с Telegram API."


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


async def answer_inline_query(
    bot_token: str,
    inline_query_id: str,
    results: list[dict[str, Any]],
    *,
    cache_time: int = 0,
    is_personal: bool = True,
) -> bool:
    payload: dict[str, Any] = {
        "inline_query_id": inline_query_id,
        "results": results,
        "cache_time": max(0, int(cache_time)),
        "is_personal": is_personal,
    }
    return (await call_bot_api(bot_token, "answerInlineQuery", payload=payload)) is not None


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
        "allowed_updates": ["message", "callback_query", "inline_query", "chosen_inline_result"],
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
            return False, format_telegram_connect_error(
                str(data.get("description") or "setWebhook failed"),
                operation="подключить бота к панели",
            )
    except Exception as exc:
        return False, format_telegram_connect_error(
            str(exc), operation="подключить бота к панели"
        )


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
            return False, format_telegram_connect_error(
                str(data.get("description") or "deleteWebhook failed"),
                operation="отключить бота от панели",
            )
    except Exception as exc:
        return False, format_telegram_connect_error(
            str(exc), operation="отключить бота от панели"
        )


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
            return False, format_telegram_connect_error(
                str(data.get("description") or "deleteWebhook failed"),
                operation="отключить бота от панели",
            )
    except Exception as exc:
        return False, format_telegram_connect_error(
            str(exc), operation="отключить бота от панели"
        )


def set_webhook_sync(bot_token: str, url: str, *, secret_token: str | None = None) -> tuple[bool, str]:
    payload: dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message", "callback_query", "inline_query", "chosen_inline_result"],
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
            return False, format_telegram_connect_error(
                str(data.get("description") or "setWebhook failed"),
                operation="подключить бота к панели",
            )
    except Exception as exc:
        return False, format_telegram_connect_error(
            str(exc), operation="подключить бота к панели"
        )


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
            return False, format_telegram_connect_error(
                str(data.get("description") or "setMyCommands failed"),
                operation="настроить команды бота",
            )
    except Exception as exc:
        return False, format_telegram_connect_error(
            str(exc), operation="настроить команды бота"
        )


def reset_chat_menu_button_sync(bot_token: str) -> tuple[bool, str]:
    """Reset bot chat menu button to Telegram default (removes Web App launcher)."""
    payload = {"menu_button": {"type": "default"}}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.post(
                _API_BASE.format(token=bot_token, method="setChatMenuButton"),
                json=payload,
            )
            data = response.json()
            if data.get("ok"):
                return True, ""
            return False, format_telegram_connect_error(
                str(data.get("description") or "setChatMenuButton failed"),
                operation="сбросить кнопку меню бота",
            )
    except Exception as exc:
        return False, format_telegram_connect_error(
            str(exc), operation="сбросить кнопку меню бота"
        )
