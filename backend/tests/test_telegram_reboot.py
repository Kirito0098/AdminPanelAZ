import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import NodeStatus
from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers import settings_maintenance as mnt


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


def _node(*, node_id: int = 42, name: str = "vpn-a"):
    node = MagicMock()
    node.id = node_id
    node.name = name
    node.status = NodeStatus.online
    node.node_kind = "vpn"
    return node


def test_reboot_phrase_schedules():
    ctx = _ctx()
    settings_fsm.set_pending("1", "mnt_reboot")
    settings_fsm.set_pending_value("1", "42")
    execute_at = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)

    with patch.object(mnt, "_require_admin_ctx", new=AsyncMock(return_value=True)), patch(
        "app.services.telegram_bot_handlers.settings_maintenance.send_message", new=AsyncMock()
    ), patch(
        "app.services.telegram_bot_handlers.settings_maintenance.schedule_server_reboot"
    ) as sched, patch(
        "app.services.telegram_bot_handlers.settings_maintenance._make_bot_request", return_value=MagicMock()
    ), patch(
        "app.services.telegram_bot_handlers.settings_maintenance._log_bot_action"
    ):
        sched.return_value = MagicMock(
            reboot_id="r1",
            node_name="vpn-a",
            delay_seconds=15,
            execute_at=execute_at,
            warning=None,
        )
        ok = asyncio.run(mnt.handle_maintenance_text(ctx, "REBOOT"))
        assert ok is True
        sched.assert_called_once()
        assert settings_fsm.get_pending("1") is None


def test_reboot_wrong_phrase_keeps_fsm():
    ctx = _ctx()
    settings_fsm.set_pending("1", "mnt_reboot")
    settings_fsm.set_pending_value("1", "42")

    with patch.object(mnt, "_require_admin_ctx", new=AsyncMock(return_value=True)), patch(
        "app.services.telegram_bot_handlers.settings_maintenance.send_message", new=AsyncMock()
    ) as send, patch(
        "app.services.telegram_bot_handlers.settings_maintenance.schedule_server_reboot"
    ) as sched:
        ok = asyncio.run(mnt.handle_maintenance_text(ctx, "reboot"))
        assert ok is True
        sched.assert_not_called()
        send.assert_called_once()
        assert settings_fsm.get_pending("1") is not None


def test_reboot_callback_lists_nodes():
    ctx = _ctx()
    node = _node()

    with patch.object(mnt, "_require_admin_ctx", new=AsyncMock(return_value=True)), patch(
        "app.services.telegram_bot_handlers.settings_maintenance._list_nodes", return_value=[node]
    ), patch(
        "app.services.telegram_bot_handlers.settings_maintenance._send_or_edit", new=AsyncMock()
    ) as edit:
        asyncio.run(mnt.handle_maintenance_callback(ctx, "st:mnt:reboot", message_id=10))
        edit.assert_called_once()
        markup = edit.call_args.kwargs["markup"]
        assert markup["inline_keyboard"][0][0]["callback_data"] == "st:mnt:reboot:n:42"


def test_reboot_ask_sets_fsm():
    ctx = _ctx()
    node = _node()

    with patch.object(mnt, "_require_admin_ctx", new=AsyncMock(return_value=True)), patch(
        "app.services.telegram_bot_handlers.settings_maintenance._get_node", return_value=node
    ), patch(
        "app.services.telegram_bot_handlers.settings_maintenance.send_message", new=AsyncMock()
    ):
        asyncio.run(mnt.handle_maintenance_callback(ctx, "st:mnt:reboot:ask:42", message_id=None))
        pending = settings_fsm.get_pending("1")
        assert pending is not None
        assert pending.field == "mnt_reboot"
        assert pending.value == "42"


def test_reboot_cancel_calls_api():
    ctx = _ctx()

    with patch.object(mnt, "_require_admin_ctx", new=AsyncMock(return_value=True)), patch(
        "app.services.telegram_bot_handlers.settings_maintenance.cancel_server_reboot"
    ) as cancel, patch(
        "app.services.telegram_bot_handlers.settings_maintenance._make_bot_request", return_value=MagicMock()
    ), patch(
        "app.services.telegram_bot_handlers.settings_maintenance._log_bot_action"
    ), patch(
        "app.services.telegram_bot_handlers.settings_maintenance.send_message", new=AsyncMock()
    ) as send:
        cancel.return_value = MagicMock(node_id=42, node_name="vpn-a")
        asyncio.run(mnt.handle_maintenance_callback(ctx, "st:mnt:reboot:cancel:r1", message_id=None))
        cancel.assert_called_once_with("r1", cancel.call_args[0][1], ctx.db, ctx.user)
        send.assert_called_once()
