"""Tests for /settings -> Backups preset callbacks."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import UserRole
from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers.settings_backups import (
    _backup_main_keyboard,
    handle_backups_callback,
)


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.user = SimpleNamespace(id=1, username="admin", role=UserRole.admin)
    ctx.telegram_user_id = "42"
    ctx.bot_token = "bot-token"
    ctx.chat_id = 777
    ctx.db = MagicMock()
    ctx.settings = MagicMock()
    ctx.mini_app_url = "https://panel.example/api/tg-mini"
    return ctx


def test_backup_keyboard_has_days_and_retention_presets():
    settings = MagicMock(
        auto_backup_enabled=True,
        telegram_on_backup=False,
        backup_az_enabled=True,
    )

    kb = _backup_main_keyboard(settings)
    callbacks = [btn["callback_data"] for row in kb["inline_keyboard"] for btn in row]

    for value in (1, 3, 7, 14):
        assert f"st:bk:days:{value}" in callbacks
    for value in (3, 5, 7, 14):
        assert f"st:bk:ret:{value}" in callbacks
    assert "st:bk:ask:days" in callbacks
    assert "st:bk:ask:ret" in callbacks


def test_handle_backups_days_preset_updates_settings():
    ctx = _ctx()

    with (
        patch(
            "app.services.telegram_bot_handlers.settings_backups._require_admin_ctx",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.telegram_bot_handlers.settings_backups._apply_backup_settings_patch",
        ) as apply_patch,
        patch(
            "app.services.telegram_bot_handlers.settings_backups.handle_settings_backups",
            new=AsyncMock(),
        ) as refresh,
    ):
        asyncio.run(handle_backups_callback(ctx, "st:bk:days:7", message_id=99))

    payload = apply_patch.call_args.args[1]
    assert payload.auto_backup_days == 7
    assert payload.retention_count is None
    assert apply_patch.call_args.kwargs["log_details"] == "field=bk_days; value=7"
    refresh.assert_awaited_once_with(ctx, message_id=99)


def test_handle_backups_retention_preset_updates_settings():
    ctx = _ctx()

    with (
        patch(
            "app.services.telegram_bot_handlers.settings_backups._require_admin_ctx",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.telegram_bot_handlers.settings_backups._apply_backup_settings_patch",
        ) as apply_patch,
        patch(
            "app.services.telegram_bot_handlers.settings_backups.handle_settings_backups",
            new=AsyncMock(),
        ) as refresh,
    ):
        asyncio.run(handle_backups_callback(ctx, "st:bk:ret:5", message_id=11))

    payload = apply_patch.call_args.args[1]
    assert payload.retention_count == 5
    assert payload.auto_backup_days is None
    assert apply_patch.call_args.kwargs["log_details"] == "field=bk_ret; value=5"
    refresh.assert_awaited_once_with(ctx, message_id=11)


def test_handle_backups_invalid_preset_value_is_rejected():
    ctx = _ctx()

    with (
        patch(
            "app.services.telegram_bot_handlers.settings_backups._require_admin_ctx",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.telegram_bot_handlers.settings_backups._apply_backup_settings_patch",
        ) as apply_patch,
        patch(
            "app.services.telegram_bot_handlers.settings_backups.handle_settings_backups",
            new=AsyncMock(),
        ) as refresh,
        patch(
            "app.services.telegram_bot_handlers.settings_backups.send_message",
            new=AsyncMock(),
        ) as send,
    ):
        asyncio.run(handle_backups_callback(ctx, "st:bk:days:2", message_id=5))

    apply_patch.assert_not_called()
    refresh.assert_not_awaited()
    send.assert_awaited_once()
    assert "❌" in send.await_args.args[2]


def test_handle_backups_ask_days_keeps_custom_fsm_flow():
    ctx = _ctx()
    settings_fsm.clear_all()

    with (
        patch(
            "app.services.telegram_bot_handlers.settings_backups._require_admin_ctx",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.telegram_bot_handlers.settings_backups.send_message",
            new=AsyncMock(),
        ) as send,
    ):
        asyncio.run(handle_backups_callback(ctx, "st:bk:ask:days", message_id=3))

    pending = settings_fsm.get_pending(ctx.telegram_user_id)
    assert pending is not None
    assert pending.field == "bk_days"
    assert "Введите интервал авто-бэкапа, дней" in send.await_args.args[2]
    assert send.await_args.kwargs["reply_markup"] == {"force_reply": True, "selective": True}
    settings_fsm.clear_all()
