"""The interactive bot must answer only in private chats (never leak configs into groups/channels)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.telegram_bot import TelegramBotService
from app.services.telegram_bot_handlers.base import TelegramBotSettingsSnapshot

_SNAP = TelegramBotSettingsSnapshot(
    bot_token="bot-token",
    interactive_enabled=True,
    bot_username="bot",
    webhook_set_at="",
    webhook_secret_set=True,
    token_set=True,
)


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setattr("app.services.telegram_bot.load_telegram_bot_settings_snapshot", lambda _db: _SNAP)
    monkeypatch.setattr(
        "app.services.telegram_bot.resolve_user",
        lambda _db, _tg_id: MagicMock(is_active=True, role="admin"),
    )
    answer = AsyncMock()
    monkeypatch.setattr("app.services.telegram_bot.answer_callback_query", answer)
    dispatch_command = AsyncMock()
    monkeypatch.setattr("app.services.telegram_bot._dispatch_command", dispatch_command)
    dispatch_callback = AsyncMock()
    monkeypatch.setattr("app.services.telegram_bot._dispatch_callback", dispatch_callback)
    return MagicMock(answer=answer, command=dispatch_command, callback=dispatch_callback)


def _run(update: dict) -> None:
    asyncio.run(TelegramBotService().handle_update(MagicMock(), update, mini_app_url="https://p/api/tg-mini"))


def _message(chat_type: str) -> dict:
    return {"message": {"text": "/configs", "from": {"id": 42}, "chat": {"id": -100 if chat_type != "private" else 42, "type": chat_type}}}


def _callback(chat_type: str) -> dict:
    return {
        "callback_query": {
            "id": "cb",
            "data": "configs",
            "from": {"id": 42},
            "message": {"message_id": 1, "chat": {"id": -100, "type": chat_type}},
        }
    }


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
def test_commands_ignored_outside_private_chat(bot, chat_type):
    _run(_message(chat_type))
    bot.command.assert_not_awaited()


def test_commands_handled_in_private_chat(bot):
    _run(_message("private"))
    bot.command.assert_awaited_once()


@pytest.mark.parametrize("chat_type", ["group", "supergroup"])
def test_callbacks_ignored_outside_private_chat(bot, chat_type):
    _run(_callback(chat_type))
    bot.callback.assert_not_awaited()
    bot.answer.assert_awaited_once()


def test_callbacks_handled_in_private_chat(bot):
    _run(_callback("private"))
    bot.callback.assert_awaited_once()
