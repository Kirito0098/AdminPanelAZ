import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers import settings_security as sec


@pytest.fixture(autouse=True)
def _fsm():
    settings_fsm.clear_all()
    yield
    settings_fsm.clear_all()


def _ctx(*, uid: str = "1") -> MagicMock:
    ctx = MagicMock()
    ctx.telegram_user_id = uid
    ctx.bot_token = "t"
    ctx.chat_id = 1
    ctx.db = MagicMock()
    ctx.user = MagicMock(username="admin", id=1)
    return ctx


def test_security_menu_opens_and_keeps_toggle_callbacks():
    ctx = _ctx()

    with patch.object(sec, "_require_admin_ctx", new=AsyncMock(return_value=True)), patch(
        "app.services.telegram_bot_handlers.settings_security._get_security",
        return_value={
            "allowed_ips": [],
            "temp_whitelist": [],
            "whitelist_firewall_active": False,
            "ip_restriction_enabled": False,
            "block_scanners": True,
        },
    ), patch(
        "app.services.telegram_bot_handlers.settings_security._get_scanner_bans",
        return_value=[],
    ), patch(
        "app.services.telegram_bot_handlers.settings_security._send_or_edit",
        new=AsyncMock(),
    ) as send:
        asyncio.run(sec.handle_settings_security(ctx, message_id=10))

    send.assert_called_once()
    text = send.await_args.args[1]
    markup = send.await_args.kwargs["markup"]
    callbacks = [
        btn["callback_data"]
        for row in markup["inline_keyboard"]
        for btn in row
        if "callback_data" in btn
    ]

    assert "🛡 <b>Безопасность</b>" in text
    assert "st:sec" in callbacks
    assert any(cb.startswith("st:sec:ip:") for cb in callbacks)
    assert any(cb.startswith("st:sec:scan:") for cb in callbacks)
    assert "st:sec:ask:allow" in callbacks
    assert "st:sec:ask:tmp" in callbacks


def test_security_ask_allow_sets_fsm_and_prompts():
    ctx = _ctx()

    with patch.object(sec, "_require_admin_ctx", new=AsyncMock(return_value=True)), patch(
        "app.services.telegram_bot_handlers.settings_security.send_message",
        new=AsyncMock(),
    ) as send:
        asyncio.run(sec.handle_security_callback(ctx, "st:sec:ask:allow", message_id=None))

    pending = settings_fsm.get_pending("1")
    assert pending is not None
    assert pending.field == "sec_allow_ip"
    send.assert_called_once()
    assert "постоянного whitelist" in send.await_args.args[2]


def test_security_ask_tmp_sets_fsm_and_prompts():
    ctx = _ctx()

    with patch.object(sec, "_require_admin_ctx", new=AsyncMock(return_value=True)), patch(
        "app.services.telegram_bot_handlers.settings_security.send_message",
        new=AsyncMock(),
    ) as send:
        asyncio.run(sec.handle_security_callback(ctx, "st:sec:ask:tmp", message_id=None))

    pending = settings_fsm.get_pending("1")
    assert pending is not None
    assert pending.field == "sec_tmp_ip"
    send.assert_called_once()
    assert "временного whitelist" in send.await_args.args[2]
