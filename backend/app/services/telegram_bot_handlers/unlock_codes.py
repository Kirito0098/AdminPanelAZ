"""Telegram bot flow for creating unlock codes."""

from __future__ import annotations

import json
import re
from html import escape

from app.services import telegram_bot_i18n as i18n
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import (
    BotContext,
    inline_button,
    inline_keyboard,
    is_admin,
    unlinked_message,
)
from app.services.telegram_bot_handlers.unlock_codes_fsm import (
    clear_pending,
    get_pending,
    set_pending,
)
from app.services.telegram_bot_handlers.ui import send_or_edit
from app.services.unlock_codes import create_unlock_code

_ALLOWED_PROTOCOLS = ("openvpn", "wireguard", "amneziawg2")
_PROTOCOL_ALIASES = {
    "ovpn": "openvpn",
    "openvpn": "openvpn",
    "wg": "wireguard",
    "wireguard": "wireguard",
    "awg": "amneziawg2",
    "awg2": "amneziawg2",
    "amneziawg2": "amneziawg2",
}
_PROTOCOL_LABELS = {
    "openvpn": "OpenVPN",
    "wireguard": "WireGuard",
    "amneziawg2": "AmneziaWG 2.0",
}
_MODE_BUTTONS = inline_keyboard(
    [
        [
            inline_button("Single", callback_data="uc:mode:single"),
            inline_button("Multi", callback_data="uc:mode:multi"),
        ],
        [inline_button("Отмена", callback_data="uc:cancel")],
    ]
)
_ROOT_BUTTONS = inline_keyboard(
    [
        [
            inline_button("30д OVPN", callback_data="uc:preset:ovpn30"),
            inline_button("30д все", callback_data="uc:preset:all30"),
        ],
        [inline_button("◀️ Назад", callback_data="nav:more")],
    ]
)
_MULTI_DEFAULT_MAX_REDEMPTIONS = 10
_FORCE_REPLY = {"force_reply": True, "selective": True}


def _protocol_label(protocol: str) -> str:
    return _PROTOCOL_LABELS.get(protocol, protocol)


def _require_enabled() -> str | None:
    if not get_feature_service().is_enabled("unlock_codes"):
        return module_disabled_message("unlock_codes")
    return None


async def _require_admin_ctx(ctx: BotContext) -> bool:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return False
    if not is_admin(ctx.user):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return False
    disabled_message = _require_enabled()
    if disabled_message:
        await send_message(ctx.bot_token, ctx.chat_id, disabled_message)
        return False
    return True


def _format_protocols(protocols: tuple[str, ...] | list[str]) -> str:
    return ", ".join(_protocol_label(protocol) for protocol in protocols)


def _parse_grant_days(text: str) -> int:
    match = re.search(r"\d+", (text or "").strip())
    if not match:
        raise ValueError("Введите срок продления в днях.")
    grant_days = int(match.group(0))
    if grant_days < 1 or grant_days > 3650:
        raise ValueError("Срок продления должен быть от 1 до 3650 дней.")
    return grant_days


def _parse_protocols(text: str) -> tuple[str, ...]:
    raw = (text or "").strip().lower()
    if not raw:
        raise ValueError("Введите протоколы для unlock-ключа.")
    if raw in {"all", "все", "all protocols", "все протоколы"}:
        return _ALLOWED_PROTOCOLS

    tokens = [part for part in re.split(r"[,\s;/|]+", raw) if part]
    protocols: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        protocol = _PROTOCOL_ALIASES.get(token)
        if protocol is None:
            raise ValueError(
                "Неизвестный протокол. Используйте OpenVPN, WireGuard, AmneziaWG2 или «все»."
            )
        if protocol in seen:
            continue
        seen.add(protocol)
        protocols.append(protocol)
    if not protocols:
        raise ValueError("Введите хотя бы один протокол.")
    return tuple(protocols)


def _parse_mode(text: str) -> str:
    raw = (text or "").strip().lower()
    if raw in {"single", "1", "one", "один", "разовый", "single-use"}:
        return "single"
    if raw in {"multi", "2", "many", "много", "мульти", "multi-use"}:
        return "multi"
    raise ValueError("Выберите режим Single или Multi.")


def _root_text() -> str:
    return (
        "🎟 <b>Создание unlock-ключа</b>\n\n"
        "Введите срок продления в днях, затем выберите протоколы и режим кода.\n"
        "Можно быстро выбрать один из пресетов ниже."
    )


def _mode_text(draft_protocols: tuple[str, ...], grant_days: int) -> str:
    return (
        "🎟 <b>Создание unlock-ключа</b>\n\n"
        f"Срок продления: <b>{grant_days}</b> дн.\n"
        f"Протоколы: <b>{_format_protocols(draft_protocols)}</b>\n\n"
        "Выберите режим кода:"
    )


def _success_text(code) -> str:
    try:
        protocols = tuple(str(item) for item in json.loads(code.protocols or "[]"))
    except Exception:
        protocols = ()
    return (
        "✅ <b>Unlock-ключ создан</b>\n\n"
        f"Код: <code>{escape(code.code)}</code>\n"
        f"Срок продления: <b>{code.grant_days}</b> дн.\n"
        f"Режим: <b>{escape(code.mode)}</b>\n"
        f"Активаций: <b>{code.max_redemptions}</b>\n"
        f"Протоколы: <b>{escape(_format_protocols(protocols))}</b>"
    )


def _start_grant_days_flow(telegram_user_id: str) -> None:
    clear_pending(telegram_user_id)
    set_pending(telegram_user_id, step="grant_days")


def _start_protocols_flow(telegram_user_id: str, *, grant_days: int) -> None:
    set_pending(telegram_user_id, step="protocols", grant_days=grant_days)


def _start_mode_flow(telegram_user_id: str, *, grant_days: int, protocols: tuple[str, ...]) -> None:
    set_pending(telegram_user_id, step="mode", grant_days=grant_days, protocols=protocols)


async def handle_unlock_codes_root(ctx: BotContext, *, message_id: int | None = None) -> None:
    if not await _require_admin_ctx(ctx):
        return
    _start_grant_days_flow(ctx.telegram_user_id)
    await send_or_edit(ctx, _root_text(), markup=_ROOT_BUTTONS, message_id=message_id)


async def handle_unlock_codes_callback(ctx: BotContext, data: str, *, message_id: int | None) -> bool:
    if not data.startswith("uc:"):
        return False
    if not await _require_admin_ctx(ctx):
        return True

    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    try:
        if action == "cancel":
            clear_pending(ctx.telegram_user_id)
            await send_or_edit(
                ctx,
                "Создание unlock-ключа отменено.",
                markup=None,
                message_id=message_id,
            )
            return True

        if action == "preset":
            preset = parts[2] if len(parts) > 2 else ""
            if preset == "ovpn30":
                protocols = ("openvpn",)
            elif preset == "all30":
                protocols = _ALLOWED_PROTOCOLS
            else:
                await send_message(ctx.bot_token, ctx.chat_id, "Неизвестный пресет unlock-ключа.")
                return True
            _start_mode_flow(ctx.telegram_user_id, grant_days=30, protocols=protocols)
            await send_or_edit(
                ctx,
                _mode_text(protocols, 30),
                markup=_MODE_BUTTONS,
                message_id=message_id,
            )
            return True

        if action != "mode":
            await send_message(ctx.bot_token, ctx.chat_id, "Неизвестное действие unlock-ключа.")
            return True

        pending = get_pending(ctx.telegram_user_id)
        if pending is None or pending.step != "mode" or pending.grant_days is None or not pending.protocols:
            await send_message(ctx.bot_token, ctx.chat_id, "Сначала задайте срок и протоколы unlock-ключа.")
            return True

        mode = parts[2] if len(parts) > 2 else ""
        normalized_mode = _parse_mode(mode)
        max_redemptions = 1 if normalized_mode == "single" else _MULTI_DEFAULT_MAX_REDEMPTIONS
        created = create_unlock_code(
            ctx.db,
            grant_days=pending.grant_days,
            protocols=list(pending.protocols),
            mode=normalized_mode,
            max_redemptions=max_redemptions,
            code_expires_at=None,
            creator=ctx.user,
        )
        clear_pending(ctx.telegram_user_id)
        await send_or_edit(ctx, _success_text(created), markup=None, message_id=message_id)
        return True
    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
        return True


async def handle_unlock_codes_text(ctx: BotContext, text: str) -> bool:
    pending = get_pending(ctx.telegram_user_id)
    if pending is None:
        return False
    if not await _require_admin_ctx(ctx):
        clear_pending(ctx.telegram_user_id)
        return True

    raw = (text or "").strip()
    if not raw:
        await send_message(ctx.bot_token, ctx.chat_id, "Значение не может быть пустым.")
        return True

    try:
        if pending.step == "grant_days":
            grant_days = _parse_grant_days(raw)
            _start_protocols_flow(ctx.telegram_user_id, grant_days=grant_days)
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                "Введите протоколы через запятую или пробел.\n"
                "Доступны: OpenVPN, WireGuard, AmneziaWG2.\n"
                "Можно написать «все».",
                reply_markup=_FORCE_REPLY,
            )
            return True

        if pending.step == "protocols":
            protocols = _parse_protocols(raw)
            _start_mode_flow(
                ctx.telegram_user_id,
                grant_days=pending.grant_days or 30,
                protocols=protocols,
            )
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                _mode_text(protocols, pending.grant_days or 30),
                reply_markup=_MODE_BUTTONS,
            )
            return True

        if pending.step == "mode":
            mode = _parse_mode(raw)
            pending = get_pending(ctx.telegram_user_id)
            if pending is None or pending.grant_days is None or not pending.protocols:
                await send_message(ctx.bot_token, ctx.chat_id, "Сначала задайте срок и протоколы unlock-ключа.")
                return True
            max_redemptions = 1 if mode == "single" else _MULTI_DEFAULT_MAX_REDEMPTIONS
            created = create_unlock_code(
                ctx.db,
                grant_days=pending.grant_days,
                protocols=list(pending.protocols),
                mode=mode,
                max_redemptions=max_redemptions,
                code_expires_at=None,
                creator=ctx.user,
            )
            clear_pending(ctx.telegram_user_id)
            await send_message(ctx.bot_token, ctx.chat_id, _success_text(created))
            return True
    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
        return True

    return False
