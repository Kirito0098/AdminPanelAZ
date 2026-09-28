"""Settings root dashboard — status summary from BotContext.settings."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import UserRole
from app.services.admin_notify import TG_NOTIFY_EVENT_GROUPS, TG_NOTIFY_EVENT_LABELS
from app.services.telegram_bot_handlers import settings_admin_notify as admin_notify_ui
from app.services.telegram_bot_handlers.base import TelegramBotSettingsSnapshot
from app.services.telegram_bot_i18n import BTN_TG_WEBHOOK_STATUS
from app.services.telegram_bot_handlers.settings import (
    _settings_root_keyboard,
    _settings_root_text,
    _telegram_keyboard,
    handle_settings_root,
)


def _snapshot(**kwargs) -> TelegramBotSettingsSnapshot:
    defaults = {
        "bot_token": "tok",
        "interactive_enabled": True,
        "bot_username": "bot",
        "webhook_set_at": "2026-01-15T12:00:00Z",
        "webhook_secret_set": True,
        "token_set": True,
    }
    defaults.update(kwargs)
    return TelegramBotSettingsSnapshot(**defaults)


def test_settings_root_text_includes_webhook_registered():
    text = _settings_root_text(_snapshot())
    assert "Webhook" in text
    assert "2026-01-15T12:00:00Z" in text


def test_settings_root_text_webhook_not_registered():
    text = _settings_root_text(_snapshot(webhook_set_at=""))
    assert "Webhook" in text
    assert "не зарегистрирован" in text


def test_settings_root_text_includes_status_lines():
    text = _settings_root_text(
        _snapshot(
            interactive_enabled=False,
            token_set=False,
            webhook_set_at="",
            webhook_secret_set=False,
        )
    )
    assert "Интерактив" in text
    assert "выкл" in text
    assert "Токен" in text
    assert "не задан" in text
    assert "Secret" in text
    assert "не зарегистрирован" in text


def test_settings_root_keyboard_has_st_tg():
    kb = _settings_root_keyboard()
    callbacks = [
        btn["callback_data"] for row in kb["inline_keyboard"] for btn in row
    ]
    assert "st:tg:wh:status" in callbacks
    assert "st:tg" in callbacks
    assert "st:an" in callbacks
    assert "st:bk" in callbacks
    assert "st:mon" in callbacks
    assert "st:sec" in callbacks
    assert "st:mnt" in callbacks
    assert "st:back" in callbacks


def test_telegram_keyboard_has_webhook_status():
    settings = MagicMock(
        notify_enabled=True,
        notify_on_backup=False,
        interactive_enabled=True,
        bot_token_set=True,
        chat_id=123,
        webhook_registered=True,
    )
    kb = _telegram_keyboard(settings)
    buttons = [btn for row in kb["inline_keyboard"] for btn in row]
    callbacks = [btn["callback_data"] for btn in buttons]
    assert "st:tg:wh:status" in callbacks
    assert any(
        btn["callback_data"] == "st:tg:wh:status" and btn["text"] == BTN_TG_WEBHOOK_STATUS
        for btn in buttons
    )


def test_telegram_keyboard_keeps_webhook_status_when_disabled():
    settings = MagicMock(
        notify_enabled=False,
        notify_on_backup=False,
        interactive_enabled=False,
        bot_token_set=False,
        chat_id=None,
        webhook_registered=False,
    )
    kb = _telegram_keyboard(settings)
    buttons = [btn for row in kb["inline_keyboard"] for btn in row]
    callbacks = [btn["callback_data"] for btn in buttons]

    assert "st:tg:wh:status" in callbacks
    assert any(
        btn["callback_data"] == "st:tg:wh:status" and btn["text"] == BTN_TG_WEBHOOK_STATUS
        for btn in buttons
    )


def test_handle_settings_root_uses_ctx_settings():
    snap = _snapshot()
    ctx = MagicMock()
    ctx.settings = snap
    ctx.user = MagicMock(role=UserRole.admin)
    ctx.telegram_user_id = "1"
    ctx.bot_token = "tok"
    ctx.chat_id = 1

    with patch(
        "app.services.telegram_bot_handlers.settings._send_or_edit",
        new=AsyncMock(),
    ) as send:
        asyncio.run(handle_settings_root(ctx))
        text = send.await_args.args[1]
        assert "Webhook" in text
        assert "2026-01-15T12:00:00Z" in text


def _admin_notify_settings(enabled: dict | None = None):
    flags = enabled or {}
    return SimpleNamespace(
        telegram_id="",
        notify_enabled=True,
        bot_token_set=True,
        events=[
            SimpleNamespace(key=key, label=label, enabled=bool(flags.get(key, False)))
            for key, label in TG_NOTIFY_EVENT_LABELS
        ],
    )


def test_admin_notify_level1_has_nine_group_buttons():
    kb = admin_notify_ui._admin_notify_keyboard(_admin_notify_settings())
    callbacks = [btn["callback_data"] for row in kb["inline_keyboard"] for btn in row]
    group_callbacks = [cb for cb in callbacks if cb.startswith("st:an:g:")]
    assert len(group_callbacks) == 9
    assert {cb.split(":")[-1] for cb in group_callbacks} == {
        group_id for group_id, _title, _icon, _keys in TG_NOTIFY_EVENT_GROUPS
    }
    assert not any(cb.startswith("st:an:p:") for cb in callbacks)
    assert "st:an:all:1" in callbacks
    assert "st:an:all:0" in callbacks


def test_admin_notify_group_toggle_off_patches_both_keys_at_once():
    settings = _admin_notify_settings({"node_offline": True, "node_sync_drift": True})
    kb = admin_notify_ui._admin_notify_keyboard(settings, group="nodes_ha")
    callbacks = [btn["callback_data"] for row in kb["inline_keyboard"] for btn in row]
    assert "st:an:e:node_offline" in callbacks
    assert "st:an:e:node_sync_drift" in callbacks
    assert "st:an:ge:nodes_ha:1" in callbacks
    assert "st:an:ge:nodes_ha:0" in callbacks
    assert "st:an" in callbacks
    text = admin_notify_ui._format_admin_notify_menu(settings, group="nodes_ha")
    assert "1/2" in text or "2/2" in text

    ctx = MagicMock()
    ctx.user = MagicMock(role=UserRole.admin)
    with (
        patch.object(admin_notify_ui, "_get_admin_notify", return_value=settings),
        patch.object(admin_notify_ui, "_apply_admin_notify_patch") as apply,
        patch.object(admin_notify_ui, "handle_settings_admin_notify", new=AsyncMock()) as nav,
    ):
        asyncio.run(
            admin_notify_ui.handle_admin_notify_callback(ctx, "st:an:ge:nodes_ha:0", message_id=7)
        )
    payload = apply.call_args.args[1]
    assert payload.events == {"node_offline": False, "node_sync_drift": False}
    assert apply.call_count == 1
    assert nav.await_args.kwargs.get("group") == "nodes_ha"
