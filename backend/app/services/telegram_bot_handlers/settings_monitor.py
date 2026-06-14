"""Telegram bot /settings → Monitoring section (Phase 3)."""

from __future__ import annotations

from fastapi import HTTPException

from app.schemas import MonitorSettingsUpdate
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard
from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers.settings import (
    _log_bot_action,
    _make_bot_request,
    _require_admin_ctx,
    _send_or_edit,
)

_FIELD_LABELS = {
    "mon_cpu": ("CPU порог, %", 1, 100),
    "mon_ram": ("RAM порог, %", 1, 100),
    "mon_int": ("Интервал проверки, сек", 10, 3600),
    "mon_cd": ("Cooldown, мин", 1, 1440),
}

_ASK_CALLBACKS = {
    "cpu": "mon_cpu",
    "ram": "mon_ram",
    "int": "mon_int",
    "cd": "mon_cd",
}


def _get_monitor_settings():
    from app.routers.settings import get_monitor_settings

    return get_monitor_settings()


def _apply_monitor_patch(ctx: BotContext, payload: MonitorSettingsUpdate, *, log_details: str):
    from app.routers.settings import update_monitor_settings

    try:
        result = update_monitor_settings(payload, _make_bot_request(ctx), ctx.db, ctx.user)
        _log_bot_action(ctx, "settings_monitor_update", log_details)
        return result
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        raise ValueError(detail) from exc


def _format_monitor_menu(settings) -> str:
    return (
        "📊 <b>Мониторинг CPU/RAM</b>\n\n"
        f"Порог CPU: <code>{settings.cpu_threshold}%</code>\n"
        f"Порог RAM: <code>{settings.ram_threshold}%</code>\n"
        f"Интервал: <code>{settings.interval_seconds}</code> сек\n"
        f"Cooldown: <code>{settings.cooldown_minutes}</code> мин\n\n"
        "<i>Значения сохраняются в .env; для полного применения может потребоваться перезапуск.</i>"
    )


def _monitor_keyboard() -> dict:
    return inline_keyboard(
        [
            [
                inline_button("✏️ CPU %", callback_data="st:mon:ask:cpu"),
                inline_button("✏️ RAM %", callback_data="st:mon:ask:ram"),
            ],
            [
                inline_button("✏️ Интервал", callback_data="st:mon:ask:int"),
                inline_button("✏️ Cooldown", callback_data="st:mon:ask:cd"),
            ],
            [
                inline_button("🔄 Обновить", callback_data="st:mon"),
                inline_button("◀️ Настройки", callback_data="st:root"),
            ],
        ]
    )


async def handle_settings_monitor(ctx: BotContext, *, message_id: int | None = None) -> None:
    if not await _require_admin_ctx(ctx):
        return
    settings = _get_monitor_settings()
    await _send_or_edit(
        ctx,
        _format_monitor_menu(settings),
        markup=_monitor_keyboard(),
        message_id=message_id,
    )


async def handle_monitor_callback(ctx: BotContext, data: str, *, message_id: int | None) -> None:
    if not await _require_admin_ctx(ctx):
        return

    rest = data[len("st:mon") :].lstrip(":")

    if rest == "":
        await handle_settings_monitor(ctx, message_id=message_id)
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


def _parse_int(raw: str, *, lo: int, hi: int) -> int | None:
    if not raw.isdigit():
        return None
    value = int(raw)
    if value < lo or value > hi:
        return None
    return value


async def handle_monitor_text(ctx: BotContext, text: str) -> bool:
    pending = settings_fsm.get_pending(ctx.telegram_user_id)
    if pending is None or not pending.field.startswith("mon_"):
        return False

    if not await _require_admin_ctx(ctx):
        settings_fsm.clear_pending(ctx.telegram_user_id)
        return True

    field = pending.field
    label, lo, hi = _FIELD_LABELS.get(field, ("значение", 1, 100))
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
    log_field = field
    if field == "mon_cpu":
        payload_kwargs["cpu_threshold"] = value
    elif field == "mon_ram":
        payload_kwargs["ram_threshold"] = value
    elif field == "mon_int":
        payload_kwargs["interval_seconds"] = value
    elif field == "mon_cd":
        payload_kwargs["cooldown_minutes"] = value

    try:
        _apply_monitor_patch(
            ctx,
            MonitorSettingsUpdate(**payload_kwargs),
            log_details=f"field={log_field}; value={value}",
        )
        await send_message(ctx.bot_token, ctx.chat_id, f"✅ {label}: {value}")
        await handle_settings_monitor(ctx)
    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
    return True
