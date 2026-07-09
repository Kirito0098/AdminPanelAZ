"""Telegram bot /settings → Backups section (Phase 3)."""

from __future__ import annotations

from fastapi import HTTPException

from app.schemas import BackupCreateRequest, BackupRestoreRequest, BackupSettingsUpdate
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard
from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_i18n import BK_RESTORE_WARN
from app.services.telegram_bot_handlers.settings import (
    _log_bot_action,
    _make_bot_request,
    _on_off,
    _require_admin_ctx,
    _send_or_edit,
)

_LIST_PAGE_SIZE = 5

_FIELD_LABELS = {
    "bk_days": ("интервал авто-бэкапа, дней", 1, 90),
    "bk_ret": ("число хранимых копий", 1, 30),
}

_ASK_CALLBACKS = {
    "days": "bk_days",
    "ret": "bk_ret",
}


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _get_backup_settings(ctx: BotContext):
    from app.routers.backups import get_backup_settings

    return get_backup_settings(ctx.db)


def _list_backups():
    from app.routers.backups import list_backups

    return list_backups()


def _apply_backup_settings_patch(ctx: BotContext, payload: BackupSettingsUpdate, *, log_details: str):
    from app.routers.backups import update_backup_settings

    try:
        result = update_backup_settings(payload, ctx.db)
        _log_bot_action(ctx, "settings_backup_update", log_details)
        return result
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        raise ValueError(detail) from exc


def _backup_at_index(index: int):
    backups = _list_backups()
    if index < 0 or index >= len(backups):
        return None, backups
    return backups[index], backups


def _format_backup_menu(settings, backups) -> str:
    lines = [
        "💾 <b>Бэкапы</b>\n",
        f"Авто-бэкап: <b>{_on_off(settings.auto_backup_enabled)}</b> "
        f"(каждые <code>{settings.auto_backup_days}</code> дн.)",
        f"TG при бэкапе: <b>{_on_off(settings.telegram_on_backup)}</b>",
        f"AZ-бэкап: <b>{_on_off(settings.backup_az_enabled)}</b>",
        f"Хранить копий: <code>{settings.retention_count}</code>",
        "",
        f"Архивов на сервере: <b>{len(backups)}</b>",
    ]
    if backups:
        lines.append("\nПоследние:")
        for entry in backups[:3]:
            lines.append(
                f"• <code>{entry.file_name}</code> ({_format_size(entry.size_bytes)})"
            )
    return "\n".join(lines)


def _backup_main_keyboard(settings) -> dict:
    auto = settings.auto_backup_enabled
    tg = settings.telegram_on_backup
    az = settings.backup_az_enabled
    rows = [
        [
            inline_button(
                f"⏰ Авто: {_on_off(auto)}",
                callback_data=f"st:bk:auto:{0 if auto else 1}",
            )
        ],
        [
            inline_button(
                f"📦 TG при бэкапе: {_on_off(tg)}",
                callback_data=f"st:bk:tg:{0 if tg else 1}",
            ),
            inline_button(
                f"🛡 AZ: {_on_off(az)}",
                callback_data=f"st:bk:az:{0 if az else 1}",
            ),
        ],
        [
            inline_button("✏️ Интервал, дн.", callback_data="st:bk:ask:days"),
            inline_button("✏️ Хранить", callback_data="st:bk:ask:ret"),
        ],
        [
            inline_button("➕ Создать", callback_data="st:bk:cfrm:create"),
            inline_button("📤 Тест TG", callback_data="st:bk:test"),
        ],
        [
            inline_button("📋 Список", callback_data="st:bk:p:0"),
            inline_button("🔄 Обновить", callback_data="st:bk"),
        ],
        [inline_button("◀️ Настройки", callback_data="st:root")],
    ]
    return inline_keyboard(rows)


def _format_backup_list(backups, *, page: int) -> str:
    total_pages = max(1, (len(backups) + _LIST_PAGE_SIZE - 1) // _LIST_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _LIST_PAGE_SIZE
    chunk = backups[start : start + _LIST_PAGE_SIZE]
    lines = [f"📋 <b>Архивы</b> (стр. {page + 1}/{total_pages})\n"]
    if not chunk:
        lines.append("Архивов нет.")
    else:
        for idx, entry in enumerate(chunk, start=start):
            lines.append(
                f"{idx + 1}. <code>{entry.file_name}</code>\n"
                f"   {_format_size(entry.size_bytes)} · {entry.created_at[:16]}"
            )
    return "\n".join(lines)


def _backup_list_keyboard(backups, *, page: int) -> dict:
    total_pages = max(1, (len(backups) + _LIST_PAGE_SIZE - 1) // _LIST_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _LIST_PAGE_SIZE
    chunk = backups[start : start + _LIST_PAGE_SIZE]

    rows: list[list] = []
    for idx, entry in enumerate(chunk, start=start):
        short = entry.file_name[:28] + "…" if len(entry.file_name) > 29 else entry.file_name
        rows.append(
            [
                inline_button(f"♻️ {short}", callback_data=f"st:bk:cfrm:rst:{idx}"),
                inline_button("🗑", callback_data=f"st:bk:cfrm:del:{idx}"),
            ]
        )

    nav: list = []
    if page > 0:
        nav.append(inline_button("◀️", callback_data=f"st:bk:p:{page - 1}"))
    if page < total_pages - 1:
        nav.append(inline_button("▶️", callback_data=f"st:bk:p:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([inline_button("◀️ Бэкапы", callback_data="st:bk")])
    return inline_keyboard(rows)


async def handle_settings_backups(ctx: BotContext, *, message_id: int | None = None) -> None:
    if not await _require_admin_ctx(ctx):
        return
    settings = _get_backup_settings(ctx)
    backups = _list_backups()
    await _send_or_edit(
        ctx,
        _format_backup_menu(settings, backups),
        markup=_backup_main_keyboard(settings),
        message_id=message_id,
    )


async def _show_backup_list(ctx: BotContext, *, page: int, message_id: int | None) -> None:
    backups = _list_backups()
    await _send_or_edit(
        ctx,
        _format_backup_list(backups, page=page),
        markup=_backup_list_keyboard(backups, page=page),
        message_id=message_id,
    )


async def handle_backups_callback(ctx: BotContext, data: str, *, message_id: int | None) -> None:
    if not await _require_admin_ctx(ctx):
        return

    rest = data[len("st:bk") :].lstrip(":")

    try:
        if rest == "":
            await handle_settings_backups(ctx, message_id=message_id)
            return

        if rest.startswith("p:"):
            page = int(rest.split(":", 1)[1]) if rest.split(":", 1)[1].isdigit() else 0
            await _show_backup_list(ctx, page=page, message_id=message_id)
            return

        if rest.startswith("auto:"):
            enabled = rest.endswith(":1")
            _apply_backup_settings_patch(
                ctx,
                BackupSettingsUpdate(auto_backup_enabled=enabled),
                log_details=f"field=auto_backup_enabled; value={enabled}",
            )
            await handle_settings_backups(ctx, message_id=message_id)
            return

        if rest.startswith("tg:"):
            enabled = rest.endswith(":1")
            _apply_backup_settings_patch(
                ctx,
                BackupSettingsUpdate(telegram_on_backup=enabled),
                log_details=f"field=telegram_on_backup; value={enabled}",
            )
            await handle_settings_backups(ctx, message_id=message_id)
            return

        if rest.startswith("az:"):
            enabled = rest.endswith(":1")
            _apply_backup_settings_patch(
                ctx,
                BackupSettingsUpdate(backup_az_enabled=enabled),
                log_details=f"field=backup_az_enabled; value={enabled}",
            )
            await handle_settings_backups(ctx, message_id=message_id)
            return

        if rest.startswith("ask:"):
            key = rest.split(":", 1)[1]
            field = _ASK_CALLBACKS.get(key)
            if not field:
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Неизвестный параметр.")
                return
            label, lo, hi = _FIELD_LABELS[field]
            settings_fsm.set_pending(ctx.telegram_user_id, field)
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                f"Введите {label} ({lo}–{hi}):",
                reply_markup={"force_reply": True, "selective": True},
            )
            return

        if rest == "cfrm:create":
            markup = inline_keyboard(
                [
                    [
                        inline_button("✅ Создать", callback_data="st:bk:do:create"),
                        inline_button("❌ Отмена", callback_data="st:bk"),
                    ]
                ]
            )
            await _send_or_edit(
                ctx,
                "Создать бэкап панели сейчас?\n(без конфигов VPN и AZ)",
                markup=markup,
                message_id=message_id,
            )
            return

        if rest == "do:create":
            from app.routers.backups import create_backup

            entry = create_backup(
                BackupCreateRequest(include_configs=False, include_antizapret_backup=False),
                _make_bot_request(ctx),
                ctx.db,
                ctx.user,
            )
            _log_bot_action(ctx, "settings_backup_create", f"file={entry.file_name}")
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ Бэкап создан: {entry.file_name}")
            await handle_settings_backups(ctx)
            return

        if rest == "test":
            from app.routers.backups import test_backup_telegram
            from app.schemas import BackupTestTelegramRequest

            backup_settings = _get_backup_settings(ctx)
            result = test_backup_telegram(
                BackupTestTelegramRequest(include_antizapret_backup=backup_settings.backup_az_enabled),
                db=ctx.db,
                admin=ctx.user,
            )
            _log_bot_action(ctx, "settings_backup_test_telegram", "action=test")
            message = result.get("message") if isinstance(result, dict) else "Задача поставлена в очередь"
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ {message}")
            return

        if rest.startswith("cfrm:del:"):
            idx = int(rest.split(":", 2)[2]) if rest.split(":", 2)[2].isdigit() else -1
            entry, _ = _backup_at_index(idx)
            if entry is None:
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Архив не найден.")
                return
            markup = inline_keyboard(
                [
                    [
                        inline_button("✅ Удалить", callback_data=f"st:bk:do:del:{idx}"),
                        inline_button("❌ Отмена", callback_data=f"st:bk:p:{idx // _LIST_PAGE_SIZE}"),
                    ]
                ]
            )
            await _send_or_edit(
                ctx,
                f"⚠️ Удалить архив?\n<code>{entry.file_name}</code>",
                markup=markup,
                message_id=message_id,
            )
            return

        if rest.startswith("do:del:"):
            idx = int(rest.split(":", 2)[2]) if rest.split(":", 2)[2].isdigit() else -1
            entry, _ = _backup_at_index(idx)
            if entry is None:
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Архив не найден.")
                return
            from app.routers.backups import delete_backup

            delete_backup(entry.file_name)
            _log_bot_action(ctx, "settings_backup_delete", f"file={entry.file_name}")
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ Удалён: {entry.file_name}")
            await _show_backup_list(ctx, page=idx // _LIST_PAGE_SIZE, message_id=message_id)
            return

        if rest.startswith("cfrm:rst:"):
            idx = int(rest.split(":", 2)[2]) if rest.split(":", 2)[2].isdigit() else -1
            entry, _ = _backup_at_index(idx)
            if entry is None:
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Архив не найден.")
                return
            markup = inline_keyboard(
                [
                    [
                        inline_button("✅ Восстановить", callback_data=f"st:bk:do:rst:{idx}"),
                        inline_button("❌ Отмена", callback_data=f"st:bk:p:{idx // _LIST_PAGE_SIZE}"),
                    ]
                ]
            )
            await _send_or_edit(
                ctx,
                "⚠️ <b>Восстановить из бэкапа?</b>\n"
                f"<code>{entry.file_name}</code>\n\n"
                f"{BK_RESTORE_WARN}",
                markup=markup,
                message_id=message_id,
            )
            return

        if rest.startswith("do:rst:"):
            idx = int(rest.split(":", 2)[2]) if rest.split(":", 2)[2].isdigit() else -1
            entry, _ = _backup_at_index(idx)
            if entry is None:
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Архив не найден.")
                return
            from app.routers.backups import RESTORE_RESTART_MESSAGE, restore_backup

            restore_backup(
                BackupRestoreRequest(file_name=entry.file_name),
                _make_bot_request(ctx),
                ctx.db,
                ctx.user,
            )
            _log_bot_action(ctx, "settings_backup_restore", f"file={entry.file_name}")
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                f"✅ Восстановлено: {entry.file_name}\n{RESTORE_RESTART_MESSAGE}",
            )
            return

    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
        return
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {detail}")
        return


def _parse_int(raw: str, *, lo: int, hi: int) -> int | None:
    if not raw.isdigit():
        return None
    value = int(raw)
    if value < lo or value > hi:
        return None
    return value


async def handle_backups_text(ctx: BotContext, text: str) -> bool:
    pending = settings_fsm.get_pending(ctx.telegram_user_id)
    if pending is None or not pending.field.startswith("bk_"):
        return False

    if not await _require_admin_ctx(ctx):
        settings_fsm.clear_pending(ctx.telegram_user_id)
        return True

    field = pending.field
    label, lo, hi = _FIELD_LABELS.get(field, ("значение", 1, 30))
    raw = (text or "").strip()
    value = _parse_int(raw, lo=lo, hi=hi)
    if value is None:
        await send_message(
            ctx.bot_token,
            ctx.chat_id,
            f"Введите целое число от {lo} до {hi} ({label}).",
        )
        return True

    settings_fsm.clear_pending(ctx.telegram_user_id)
    payload_kwargs: dict[str, int] = {}
    if field == "bk_days":
        payload_kwargs["auto_backup_days"] = value
    elif field == "bk_ret":
        payload_kwargs["retention_count"] = value

    try:
        _apply_backup_settings_patch(
            ctx,
            BackupSettingsUpdate(**payload_kwargs),
            log_details=f"field={field}; value={value}",
        )
        await send_message(ctx.bot_token, ctx.chat_id, f"✅ {label}: {value}")
        await handle_settings_backups(ctx)
    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
    return True
