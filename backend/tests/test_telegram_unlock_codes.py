"""Telegram bot unlock-code creation flow."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import UserRole
from app.services.telegram_bot_handlers import unlock_codes_fsm
from app.services.telegram_bot_handlers.menu import build_bot_commands
from app.services.telegram_bot_handlers.unlock_codes import (
    handle_unlock_codes_callback,
    handle_unlock_codes_root,
    handle_unlock_codes_text,
)


def _ctx(*, role: UserRole = UserRole.admin) -> MagicMock:
    ctx = MagicMock()
    ctx.user = SimpleNamespace(id=1, username="admin", role=role)
    ctx.telegram_user_id = "42"
    ctx.bot_token = "bot-token"
    ctx.chat_id = 777
    ctx.db = MagicMock()
    ctx.settings = MagicMock()
    ctx.mini_app_url = "https://panel.example/api/tg-mini"
    return ctx


def setup_function() -> None:
    unlock_codes_fsm.clear_all()


def teardown_function() -> None:
    unlock_codes_fsm.clear_all()


def test_unlock_root_denies_non_admin():
    ctx = _ctx(role=UserRole.user)

    with patch(
        "app.services.telegram_bot_handlers.unlock_codes.send_message",
        new=AsyncMock(),
    ) as send:
        asyncio.run(handle_unlock_codes_root(ctx))

    send.assert_awaited_once()
    assert "Команда доступна только администратору." in send.await_args.args[2]


def test_unlock_callback_denies_non_admin():
    ctx = _ctx(role=UserRole.user)

    with patch(
        "app.services.telegram_bot_handlers.unlock_codes.send_message",
        new=AsyncMock(),
    ) as send:
        asyncio.run(handle_unlock_codes_callback(ctx, "uc:mode:single", message_id=17))

    send.assert_awaited_once()
    assert "Команда доступна только администратору." in send.await_args.args[2]


def test_unlock_text_denies_non_admin():
    ctx = _ctx(role=UserRole.user)
    unlock_codes_fsm.set_pending(ctx.telegram_user_id, step="grant_days")

    with patch(
        "app.services.telegram_bot_handlers.unlock_codes.send_message",
        new=AsyncMock(),
    ) as send:
        asyncio.run(handle_unlock_codes_text(ctx, "30"))

    send.assert_awaited_once()
    assert "Команда доступна только администратору." in send.await_args.args[2]
    assert unlock_codes_fsm.get_pending(ctx.telegram_user_id) is None


def test_unlock_command_is_registered():
    commands = build_bot_commands()
    assert any(item["command"] == "unlock" for item in commands)


def test_unlock_flow_creates_code_after_mode_choice():
    ctx = _ctx()
    created = SimpleNamespace(
        code="ABCD-EFGH-IJKL",
        grant_days=30,
        mode="single",
        max_redemptions=1,
        protocols=json.dumps(["openvpn", "wireguard"]),
    )

    with (
        patch(
            "app.services.telegram_bot_handlers.unlock_codes.send_message",
            new=AsyncMock(),
        ),
        patch(
            "app.services.telegram_bot_handlers.unlock_codes.send_or_edit",
            new=AsyncMock(),
        ) as send_or_edit,
        patch(
            "app.services.telegram_bot_handlers.unlock_codes.create_unlock_code",
            return_value=created,
        ) as create_code,
    ):
        asyncio.run(handle_unlock_codes_root(ctx))
        pending = unlock_codes_fsm.get_pending(ctx.telegram_user_id)
        assert pending is not None
        assert pending.step == "grant_days"

        asyncio.run(handle_unlock_codes_text(ctx, "30"))
        pending = unlock_codes_fsm.get_pending(ctx.telegram_user_id)
        assert pending is not None
        assert pending.step == "protocols"
        assert pending.grant_days == 30

        asyncio.run(handle_unlock_codes_text(ctx, "ovpn, wg"))
        pending = unlock_codes_fsm.get_pending(ctx.telegram_user_id)
        assert pending is not None
        assert pending.step == "mode"
        assert pending.protocols == ("openvpn", "wireguard")

        asyncio.run(handle_unlock_codes_callback(ctx, "uc:mode:single", message_id=17))

    create_code.assert_called_once()
    payload = create_code.call_args.kwargs
    assert payload["grant_days"] == 30
    assert payload["protocols"] == ["openvpn", "wireguard"]
    assert payload["mode"] == "single"
    assert payload["max_redemptions"] == 1
    assert payload["code_expires_at"] is None
    assert payload["creator"] == ctx.user
    assert unlock_codes_fsm.get_pending(ctx.telegram_user_id) is None
    send_or_edit.assert_awaited()
    assert "<code>ABCD-EFGH-IJKL</code>" in send_or_edit.await_args.args[1]
