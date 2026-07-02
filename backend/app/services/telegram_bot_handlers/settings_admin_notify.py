"""Telegram bot /settings → AdminNotify section (Phase 3)."""

from __future__ import annotations

from fastapi import HTTPException

from app.schemas import AdminNotifySettingsUpdate
from app.services import telegram_bot_i18n as i18n
from app.services.admin_notify import TG_NOTIFY_EVENT_LABELS
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard
from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers.settings import (
    _log_bot_action,
    _on_off,
    _require_admin_ctx,
    _send_or_edit,
    _yes_no,
)

_EVENTS_PER_PAGE = 5
_EVENT_KEYS = [key for key, _ in TG_NOTIFY_EVENT_LABELS]
_EVENT_LABELS = dict(TG_NOTIFY_EVENT_LABELS)


def _get_admin_notify(ctx: BotContext):
    from app.routers.maintenance import _admin_notify_settings_response

    return _admin_notify_settings_response(ctx.db, ctx.user)


def _events_map(settings) -> dict[str, bool]:
    return {item.key: item.enabled for item in settings.events}


def _apply_admin_notify_patch(ctx: BotContext, payload: AdminNotifySettingsUpdate, *, log_details: str):
    from app.routers.maintenance import update_admin_notify_settings

    try:
        result = update_admin_notify_settings(payload, ctx.db, ctx.user)
        _log_bot_action(ctx, "settings_admin_notify_update", log_details)
        ctx.db.refresh(ctx.user)
        return result
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        raise ValueError(detail) from exc


def _total_pages() -> int:
    return max(1, (len(_EVENT_KEYS) + _EVENTS_PER_PAGE - 1) // _EVENTS_PER_PAGE)


def _format_admin_notify_menu(settings, *, page: int) -> str:
    events = _events_map(settings)
    enabled_count = sum(1 for key in _EVENT_KEYS if events.get(key))
    tg_id = settings.telegram_id or "(не задан)"
    total_pages = _total_pages()
    page = max(0, min(page, total_pages - 1))
    return (
        "🔔 <b>Уведомления администратору</b>\n\n"
        f"Telegram ID: <code>{tg_id}</code>\n"
        f"Глоб. TG-уведомления: <b>{_on_off(settings.notify_enabled)}</b>\n"
        f"Токен бота: {_yes_no(settings.bot_token_set)} "
        f"{'задан' if settings.bot_token_set else 'не задан'}\n"
        f"Включено событий: <b>{enabled_count}/{len(_EVENT_KEYS)}</b>\n\n"
        f"Стр. {page + 1}/{total_pages} — нажмите для переключения:"
    )


def _admin_notify_keyboard(settings, *, page: int) -> dict:
    events = _events_map(settings)
    total_pages = _total_pages()
    page = max(0, min(page, total_pages - 1))
    start = page * _EVENTS_PER_PAGE
    chunk = _EVENT_KEYS[start : start + _EVENTS_PER_PAGE]

    rows: list[list] = []
    for key in chunk:
        enabled = events.get(key, False)
        label = _EVENT_LABELS.get(key, key)
        mark = "✓" if enabled else "✗"
        rows.append(
            [
                inline_button(
                    f"{mark} {label}",
                    callback_data=f"st:an:e:{key}",
                )
            ]
        )

    nav: list = []
    if page > 0:
        nav.append(inline_button("◀️", callback_data=f"st:an:p:{page - 1}"))
    if page < total_pages - 1:
        nav.append(inline_button("▶️", callback_data=f"st:an:p:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append(
        [
            inline_button("✏️ Telegram ID", callback_data="st:an:ask:tgid"),
            inline_button("📱 Мой ID", callback_data="st:an:me"),
        ]
    )
    if settings.telegram_id and settings.bot_token_set:
        rows.append([inline_button("📤 Тест", callback_data="st:an:test")])
    rows.append(
        [
            inline_button("✅ Все ВКЛ", callback_data="st:an:all:1"),
            inline_button("❌ Все ВЫКЛ", callback_data="st:an:all:0"),
        ]
    )
    rows.extend(
        [
            [inline_button("🔄 Обновить", callback_data=f"st:an:p:{page}")],
            [inline_button("◀️ Настройки", callback_data="st:root")],
        ]
    )
    return inline_keyboard(rows)


async def handle_settings_admin_notify(ctx: BotContext, *, page: int = 0, message_id: int | None = None) -> None:
    if not await _require_admin_ctx(ctx):
        return
    settings = _get_admin_notify(ctx)
    await _send_or_edit(
        ctx,
        _format_admin_notify_menu(settings, page=page),
        markup=_admin_notify_keyboard(settings, page=page),
        message_id=message_id,
    )


async def handle_admin_notify_callback(ctx: BotContext, data: str, *, message_id: int | None) -> None:
    if not await _require_admin_ctx(ctx):
        return

    rest = data[len("st:an") :].lstrip(":")

    try:
        if rest.startswith("p:"):
            page = int(rest.split(":", 1)[1]) if rest.split(":", 1)[1].isdigit() else 0
            await handle_settings_admin_notify(ctx, page=page, message_id=message_id)
            return

        if rest == "" or rest == "p:0":
            await handle_settings_admin_notify(ctx, page=0, message_id=message_id)
            return

        if rest.startswith("e:"):
            key = rest.split(":", 1)[1]
            if key not in _EVENT_KEYS:
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Неизвестное событие.")
                return
            settings = _get_admin_notify(ctx)
            events = _events_map(settings)
            new_value = not events.get(key, False)
            page = _EVENT_KEYS.index(key) // _EVENTS_PER_PAGE
            _apply_admin_notify_patch(
                ctx,
                AdminNotifySettingsUpdate(events={key: new_value}),
                log_details=f"field=event:{key}; value={new_value}",
            )
            await handle_settings_admin_notify(ctx, page=page, message_id=message_id)
            return

        if rest.startswith("all:"):
            enabled = rest.endswith(":1")
            events = {key: enabled for key in _EVENT_KEYS}
            _apply_admin_notify_patch(
                ctx,
                AdminNotifySettingsUpdate(events=events),
                log_details=f"field=events_all; value={enabled}",
            )
            await handle_settings_admin_notify(ctx, page=0, message_id=message_id)
            return

        if rest == "ask:tgid":
            settings_fsm.set_pending(ctx.telegram_user_id, "an_tgid")
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                "Введите Telegram ID для уведомлений (или отправьте «-» для очистки):",
                reply_markup={"force_reply": True, "selective": True},
            )
            return

        if rest == "me":
            _apply_admin_notify_patch(
                ctx,
                AdminNotifySettingsUpdate(telegram_id=ctx.telegram_user_id),
                log_details=f"field=telegram_id; value={ctx.telegram_user_id}",
            )
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ Telegram ID: {ctx.telegram_user_id}")
            await handle_settings_admin_notify(ctx, message_id=message_id)
            return

        if rest == "test":
            from app.routers.maintenance import test_admin_notify

            test_admin_notify(ctx.db, ctx.user)
            _log_bot_action(ctx, "settings_admin_notify_test", "action=test")
            await send_message(ctx.bot_token, ctx.chat_id, "✅ Тестовое уведомление отправлено.")
            return

    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
        return
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {detail}")
        return


async def handle_admin_notify_text(ctx: BotContext, text: str) -> bool:
    pending = settings_fsm.get_pending(ctx.telegram_user_id)
    if pending is None or pending.field != "an_tgid":
        return False

    if not await _require_admin_ctx(ctx):
        settings_fsm.clear_pending(ctx.telegram_user_id)
        return True

    raw = (text or "").strip()
    if raw in i18n.MENU_ACTIONS:
        settings_fsm.clear_pending(ctx.telegram_user_id)
        return False

    tg_id = "" if raw in {"-", "0", "clear", "очистить"} else raw
    if tg_id and not tg_id.isdigit():
        await send_message(ctx.bot_token, ctx.chat_id, "Telegram ID должен быть числом или «-» для очистки.")
        return True

    settings_fsm.clear_pending(ctx.telegram_user_id)
    try:
        _apply_admin_notify_patch(
            ctx,
            AdminNotifySettingsUpdate(telegram_id=tg_id),
            log_details=f"field=telegram_id; value={tg_id or 'cleared'}",
        )
        if tg_id:
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ Telegram ID сохранён: {tg_id}")
        else:
            await send_message(ctx.bot_token, ctx.chat_id, "✅ Telegram ID очищен.")
        await handle_settings_admin_notify(ctx)
    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
    return True
