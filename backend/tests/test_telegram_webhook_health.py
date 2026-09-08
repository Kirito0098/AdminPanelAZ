"""Webhook health formatter + Telegram settings screen."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import UserRole
from app.services.telegram_api import BotApiResult
from app.services.telegram_bot_handlers.settings import (
    _webhook_health_keyboard,
    format_webhook_health_error_text,
    format_webhook_health_text,
    handle_settings_callback,
    handle_webhook_health,
)


def _admin_ctx():
    ctx = MagicMock()
    ctx.user = MagicMock(role=UserRole.admin)
    ctx.telegram_user_id = "42"
    ctx.bot_token = "bot-token"
    ctx.chat_id = 123
    ctx.settings = MagicMock()
    return ctx


def test_format_webhook_health_text_includes_url_pending_and_error():
    text = format_webhook_health_text(
        {
            "url": "https://panel.example/api/telegram/webhook/secret",
            "pending_update_count": 7,
            "last_error_message": "Wrong response from the webhook: 502 Bad Gateway",
        }
    )

    assert "Webhook" in text
    assert "https://panel.example/api/telegram/webhook/***" in text
    assert "/secret" not in text
    assert "7" in text
    assert "502 Bad Gateway" in text


def test_format_webhook_health_text_truncates_long_last_error():
    long_error = "x" * 5000

    text = format_webhook_health_text(
        {
            "url": "https://panel.example/api/telegram/webhook/secret",
            "pending_update_count": 1,
            "last_error_message": long_error,
        }
    )

    assert len(text) <= 3500
    assert "..." in text


def test_webhook_health_keyboard_has_expected_actions():
    kb = _webhook_health_keyboard()
    callbacks = [btn["callback_data"] for row in kb["inline_keyboard"] for btn in row]

    assert "st:tg:wh:status" in callbacks
    assert "st:tg:wh:reg" in callbacks
    assert "st:tg:cfrm:wh:del" in callbacks
    assert "st:tg" in callbacks


def test_handle_webhook_health_renders_mocked_info():
    ctx = _admin_ctx()

    with (
        patch(
            "app.services.telegram_bot_handlers.settings.get_webhook_info_result",
            new=AsyncMock(
                return_value=BotApiResult(
                    ok=True,
                    result={
                        "url": "https://panel.example/api/telegram/webhook/secret",
                        "pending_update_count": 3,
                        "last_error_message": "Webhook returned 500",
                    },
                ),
            ),
        ),
        patch(
            "app.services.telegram_bot_handlers.settings._send_or_edit",
            new=AsyncMock(),
        ) as send,
    ):
        asyncio.run(handle_webhook_health(ctx, message_id=77))

    assert send.await_count == 1
    assert send.await_args.kwargs["message_id"] == 77
    text = send.await_args.args[1]
    assert "3" in text
    assert "Webhook returned 500" in text


def test_format_webhook_health_error_text_is_actionable():
    text = format_webhook_health_error_text(
        "Не удалось получить статус webhook: истекло время ожидания ответа от api.telegram.org."
    )

    assert "Не удалось получить статус webhook" in text
    assert "истекло время ожидания" in text
    assert "не зарегистрирован" not in text
    assert "исходящий доступ сервера к Telegram API" in text


def test_handle_webhook_health_renders_fetch_failure():
    ctx = _admin_ctx()

    with (
        patch(
            "app.services.telegram_bot_handlers.settings.get_webhook_info_result",
            new=AsyncMock(
                return_value=BotApiResult(
                    ok=False,
                    error="Не удалось получить статус webhook: сервер не может разрешить DNS-имя api.telegram.org.",
                )
            ),
        ),
        patch(
            "app.services.telegram_bot_handlers.settings._send_or_edit",
            new=AsyncMock(),
        ) as send,
    ):
        asyncio.run(handle_webhook_health(ctx, message_id=78))

    text = send.await_args.args[1]
    assert "Не удалось получить статус webhook" in text
    assert "DNS-имя api.telegram.org" in text
    assert "не зарегистрирован" not in text


def test_handle_settings_callback_routes_webhook_health():
    ctx = _admin_ctx()

    with patch(
        "app.services.telegram_bot_handlers.settings.handle_webhook_health",
        new=AsyncMock(),
    ) as health:
        asyncio.run(handle_settings_callback(ctx, "st:tg:wh:status", message_id=19))

    health.assert_awaited_once_with(ctx, message_id=19)
