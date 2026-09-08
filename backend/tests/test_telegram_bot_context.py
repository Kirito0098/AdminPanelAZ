"""Telegram bot settings snapshot and BotContext wiring."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.telegram_bot import TelegramBotService, _build_context
from app.services.telegram_bot_handlers.base import (
    BotContext,
    TelegramBotSettingsSnapshot,
    load_telegram_bot_settings_snapshot,
)


def _settings_map(**overrides: str) -> dict[str, str]:
    base = {
        "telegram_bot_token": "bot-token-123",
        "telegram_bot_interactive_enabled": "true",
        "telegram_bot_username": "my_bot",
        "telegram_webhook_set_at": "2026-01-01T00:00:00Z",
        "telegram_webhook_secret": "wh-secret",
    }
    base.update(overrides)
    return base


def test_load_telegram_bot_settings_snapshot_reads_expected_keys(monkeypatch):
    store = _settings_map()

    def fake_get_setting(_db, key, default=""):
        return store.get(key, default)

    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.base._get_setting",
        fake_get_setting,
    )

    db = MagicMock()
    snap = load_telegram_bot_settings_snapshot(db)

    assert snap == TelegramBotSettingsSnapshot(
        bot_token="bot-token-123",
        interactive_enabled=True,
        bot_username="my_bot",
        webhook_set_at="2026-01-01T00:00:00Z",
        webhook_secret_set=True,
        token_set=True,
    )


def test_load_telegram_bot_settings_snapshot_empty_token_and_secret(monkeypatch):
    store = _settings_map(telegram_bot_token="", telegram_webhook_secret="")

    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.base._get_setting",
        lambda _db, key, default="": store.get(key, default),
    )

    snap = load_telegram_bot_settings_snapshot(MagicMock())

    assert snap.bot_token == ""
    assert snap.token_set is False
    assert snap.webhook_secret_set is False
    assert snap.interactive_enabled is True


def test_build_context_uses_snapshot_without_refetching_token(monkeypatch):
    snap = TelegramBotSettingsSnapshot(
        bot_token="snap-token",
        interactive_enabled=True,
        bot_username="bot",
        webhook_set_at="",
        webhook_secret_set=False,
        token_set=True,
    )
    token_fetches: list[str] = []

    def spy_get_setting(_db, key, default=""):
        if key == "telegram_bot_token":
            token_fetches.append(key)
        return default

    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.base._get_setting",
        spy_get_setting,
    )
    monkeypatch.setattr(
        "app.services.telegram_bot.resolve_user",
        lambda _db, _tg_id: None,
    )

    ctx = _build_context(
        MagicMock(),
        chat_id=1,
        telegram_user_id="42",
        mini_app_url="https://panel.example/api/tg-mini",
        settings=snap,
    )

    assert ctx.bot_token == "snap-token"
    assert ctx.settings is snap
    assert token_fetches == []


def test_handle_callback_fetches_bot_token_once(monkeypatch):
    store = _settings_map()
    token_calls: list[str] = []

    def counting_get_setting(_db, key, default=""):
        if key == "telegram_bot_token":
            token_calls.append(key)
        return store.get(key, default)

    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.base._get_setting",
        counting_get_setting,
    )
    monkeypatch.setattr(
        "app.services.telegram_bot.resolve_user",
        lambda _db, _tg_id: MagicMock(is_active=True, role="admin"),
    )

    answer = AsyncMock()
    monkeypatch.setattr("app.services.telegram_bot.answer_callback_query", answer)
    dispatch = AsyncMock()
    monkeypatch.setattr("app.services.telegram_bot._dispatch_callback", dispatch)

    service = TelegramBotService()
    callback = {
        "id": "cb-1",
        "data": "help",
        "from": {"id": 99},
        "message": {"message_id": 7, "chat": {"id": 99}},
    }

    asyncio.run(
        service._handle_callback(
            MagicMock(),
            callback,
            mini_app_url="https://panel.example/api/tg-mini",
        )
    )

    assert len(token_calls) == 1
    answer.assert_awaited_once_with("bot-token-123", "cb-1")
    dispatch.assert_awaited_once()
    ctx = dispatch.await_args.args[0]
    assert isinstance(ctx, BotContext)
    assert ctx.bot_token == "bot-token-123"
