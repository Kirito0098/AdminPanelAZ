"""Unit tests for Telegram bot main menu keyboards and routing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import User, UserRole
from app.services.telegram_bot_handlers.base import BotContext
from app.services.telegram_bot_handlers.menu import (
    build_bot_commands,
    build_main_inline_menu,
    build_reply_keyboard,
    handle_menu_callback,
    handle_menu_text,
)
from app.services import telegram_bot_i18n as i18n


def _ctx(*, user: User | None = None, mini_app_url: str = "https://panel.example/api/tg-mini") -> BotContext:
    return BotContext(
        db=MagicMock(),
        bot_token="test-token",
        chat_id=123,
        telegram_user_id="123",
        user=user,
        mini_app_url=mini_app_url,
    )


def _user(role: UserRole) -> User:
    user = User(id=1, username="testuser", role=role, is_active=True)
    user.telegram_id = "123"
    return user


def test_build_reply_keyboard_unlinked():
    markup = build_reply_keyboard(_ctx(user=None))
    assert "keyboard" in markup
    labels = [btn["text"] for row in markup["keyboard"] for btn in row]
    assert labels == [i18n.BTN_MENU_HELP]


def test_build_reply_keyboard_linked_user():
    markup = build_reply_keyboard(_ctx(user=_user(UserRole.user)))
    labels = [btn["text"] for row in markup["keyboard"] for btn in row]
    assert i18n.BTN_MENU_STATUS in labels
    assert i18n.BTN_MENU_CONFIGS in labels
    assert i18n.BTN_MENU_HELP in labels
    assert i18n.BTN_MENU_SETTINGS not in labels


def test_build_reply_keyboard_admin_includes_settings_and_nodes():
    markup = build_reply_keyboard(_ctx(user=_user(UserRole.admin)))
    labels = [btn["text"] for row in markup["keyboard"] for btn in row]
    assert i18n.BTN_MENU_SETTINGS in labels
    assert i18n.BTN_MENU_NODES in labels


def test_build_reply_keyboard_admin_modules_when_enabled():
    ctx = _ctx(user=_user(UserRole.admin))
    with patch("app.services.telegram_bot_handlers.menu.get_feature_service") as gs:
        gs.return_value.is_enabled.side_effect = lambda key: key in {"routing", "warper"}
        markup = build_reply_keyboard(ctx)
    labels = [btn["text"] for row in markup["keyboard"] for btn in row]
    assert i18n.BTN_MENU_CIDR in labels
    assert i18n.BTN_MENU_WARPER in labels


def test_build_reply_keyboard_mini_app_web_app_button():
    markup = build_reply_keyboard(_ctx(user=_user(UserRole.user)))
    buttons = [btn for row in markup["keyboard"] for btn in row]
    mini = next(btn for btn in buttons if btn["text"] == i18n.BTN_OPEN_MINI_APP)
    assert mini["web_app"]["url"] == "https://panel.example/api/tg-mini"


def test_build_main_inline_menu_has_nav_callbacks():
    markup = build_main_inline_menu(_ctx(user=_user(UserRole.user)))
    callbacks = [
        btn.get("callback_data")
        for row in markup["inline_keyboard"]
        for btn in row
        if "callback_data" in btn
    ]
    assert "nav:status" in callbacks
    assert "nav:configs" in callbacks
    assert "nav:help" in callbacks


def test_build_bot_commands():
    commands = build_bot_commands()
    assert {"command": "start", "description": "Главное меню"} in commands
    assert any(item["command"] == "settings" for item in commands)


def test_handle_menu_text_status():
    ctx = _ctx(user=_user(UserRole.user))
    with patch(
        "app.services.telegram_bot_handlers.status.handle_status",
        new_callable=AsyncMock,
    ) as handle_status:
        handled = asyncio.run(handle_menu_text(ctx, i18n.BTN_MENU_STATUS))
    assert handled is True
    handle_status.assert_awaited_once_with(ctx, message_id=None)


def test_handle_menu_text_unknown():
    ctx = _ctx(user=_user(UserRole.user))
    handled = asyncio.run(handle_menu_text(ctx, "random text"))
    assert handled is False


def test_handle_menu_text_admin_only_for_viewer():
    ctx = _ctx(user=_user(UserRole.viewer))
    with patch("app.services.telegram_bot_handlers.menu.send_message", new_callable=AsyncMock) as send:
        handled = asyncio.run(handle_menu_text(ctx, i18n.BTN_MENU_SETTINGS))
    assert handled is True
    send.assert_awaited_once()
    assert i18n.ADMIN_ONLY in send.call_args.args[2]


def test_handle_menu_callback_configs():
    ctx = _ctx(user=_user(UserRole.admin))
    with patch(
        "app.services.telegram_bot_handlers.configs.handle_configs",
        new_callable=AsyncMock,
    ) as handle_configs:
        handled = asyncio.run(handle_menu_callback(ctx, "nav:configs", message_id=99))
    assert handled is True
    handle_configs.assert_awaited_once_with(ctx, message_id=99)
