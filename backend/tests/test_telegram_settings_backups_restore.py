"""Bot restore/delete buttons must target the archive the admin saw, not a list position."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import UserRole
from app.services.telegram_bot_handlers import settings_backups as sb

MOD = "app.services.telegram_bot_handlers.settings_backups"


def _entry(name: str):
    return SimpleNamespace(file_name=name, size_bytes=2048, created_at="2026-09-26T10:00:00")


OLD = _entry("backup_20260925_100000.zip")
OLDER = _entry("backup_20260924_100000.zip")
NEW = _entry("backup_20260926_120000.zip")


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.user = SimpleNamespace(id=1, username="admin", role=UserRole.admin)
    ctx.telegram_user_id = "42"
    ctx.bot_token = "bot-token"
    ctx.chat_id = 777
    return ctx


def _callbacks(markup) -> list[str]:
    return [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]


def _run(data: str, backups: list):
    restore = MagicMock()
    delete = MagicMock()
    send = AsyncMock()
    edit = AsyncMock()
    with ExitStack() as stack:
        stack.enter_context(patch(f"{MOD}._require_admin_ctx", new=AsyncMock(return_value=True)))
        stack.enter_context(patch(f"{MOD}._list_backups", return_value=backups))
        stack.enter_context(patch(f"{MOD}._make_bot_request"))
        stack.enter_context(patch(f"{MOD}._log_bot_action"))
        stack.enter_context(patch(f"{MOD}.send_message", new=send))
        stack.enter_context(patch(f"{MOD}._send_or_edit", new=edit))
        stack.enter_context(patch("app.routers.backups.restore_backup", new=restore))
        stack.enter_context(patch("app.routers.backups.delete_backup", new=delete))
        asyncio.run(sb.handle_backups_callback(_ctx(), data, message_id=5))
    return SimpleNamespace(restore=restore, delete=delete, send=send, edit=edit)


def _confirm_callback(action: str, entry, backups) -> str:
    list_cbs = _callbacks(sb._backup_list_keyboard(backups, page=0))
    idx = backups.index(entry)
    cfrm = [cb for cb in list_cbs if cb.startswith(f"st:bk:cfrm:{action}:")][idx]
    result = _run(cfrm, backups)
    return next(
        cb
        for cb in _callbacks(result.edit.call_args.kwargs["markup"])
        if cb.startswith(f"st:bk:do:{action}:")
    )


def test_restore_targets_confirmed_archive_after_list_shifts():
    do_rst = _confirm_callback("rst", OLD, [OLD, OLDER])

    result = _run(do_rst, [NEW, OLD, OLDER])

    result.restore.assert_called_once()
    assert result.restore.call_args.args[0].file_name == OLD.file_name


def test_delete_targets_confirmed_archive_after_list_shifts():
    do_del = _confirm_callback("del", OLDER, [OLD, OLDER])

    result = _run(do_del, [NEW, OLD, OLDER])

    result.delete.assert_called_once_with(OLDER.file_name)


def test_restore_of_vanished_archive_is_refused():
    do_rst = _confirm_callback("rst", OLD, [OLD, OLDER])

    result = _run(do_rst, [NEW, OLDER])

    result.restore.assert_not_called()
    assert "не найден" in result.send.call_args.args[2]


@pytest.mark.parametrize("data", ["st:bk:do:rst:0", "st:bk:do:del:1", "st:bk:do:rst:", "st:bk:do:rst:zz"])
def test_legacy_index_callbacks_do_nothing(data):
    result = _run(data, [OLD, OLDER])

    result.restore.assert_not_called()
    result.delete.assert_not_called()


def test_callback_data_fits_telegram_limit_for_long_names():
    long_entry = _entry("backup_" + "x" * 120 + ".zip")
    for cb in _callbacks(sb._backup_list_keyboard([long_entry], page=0)):
        assert len(cb.encode()) <= 64
    do_rst = _confirm_callback("rst", long_entry, [long_entry])
    assert len(do_rst.encode()) <= 64
