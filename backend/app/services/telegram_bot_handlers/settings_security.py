"""Telegram bot /settings → Security section (Phase 3)."""

from __future__ import annotations

import ipaddress

from fastapi import HTTPException

from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard
from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers.settings import (
    _log_bot_action,
    _make_bot_request,
    _on_off,
    _require_admin_ctx,
    _send_or_edit,
    _yes_no,
)


def _get_security(ctx: BotContext) -> dict:
    from app.routers.security import get_security

    return get_security(ctx.db)


def _get_scanner_bans() -> list[dict]:
    from app.routers.security import get_scanner_bans

    return get_scanner_bans().get("active_bans") or []


def _validate_ip(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        ipaddress.ip_network(raw, strict=False)
        return raw
    except ValueError:
        return None


def _format_security_menu(settings: dict, *, ban_count: int) -> str:
    allowed = settings.get("allowed_ips") or []
    temp_list = settings.get("temp_whitelist") or []
    allowed_preview = ", ".join(allowed[:5]) if allowed else "(пусто)"
    if len(allowed) > 5:
        allowed_preview += f" … +{len(allowed) - 5}"

    lines = [
        "🛡 <b>Безопасность</b>\n",
        f"IP-ограничение: <b>{_on_off(settings.get('ip_restriction_enabled'))}</b>",
        f"iptables whitelist: {_yes_no(settings.get('whitelist_firewall_active'))} "
        f"{'активен' if settings.get('whitelist_firewall_active') else 'нет'}",
        f"Блок сканеров: <b>{_on_off(settings.get('block_scanners'))}</b>",
        f"Постоянных IP: <code>{len(allowed)}</code>",
        f"Разрешённые: {allowed_preview}",
        f"Временных IP: <code>{len(temp_list)}</code>",
        f"Банов сканеров: <code>{ban_count}</code>",
    ]
    if temp_list:
        lines.append("\nВременный whitelist:")
        for row in temp_list[:3]:
            ip = row.get("ip", "?")
            hours = row.get("hours", "?")
            lines.append(f"• <code>{ip}</code> ({hours} ч.)")
    return "\n".join(lines)


def _security_keyboard(settings: dict) -> dict:
    ip_on = settings.get("ip_restriction_enabled")
    scan_on = settings.get("block_scanners")
    rows = [
        [
            inline_button(
                f"🔒 IP-ограничение: {_on_off(ip_on)}",
                callback_data=f"st:sec:ip:{0 if ip_on else 1}",
            )
        ],
        [
            inline_button(
                f"🚫 Блок сканеров: {_on_off(scan_on)}",
                callback_data=f"st:sec:scan:{0 if scan_on else 1}",
            )
        ],
        [
            inline_button("➕ IP в whitelist", callback_data="st:sec:ask:allow"),
            inline_button("⏱ Temp IP", callback_data="st:sec:ask:tmp"),
        ],
        [
            inline_button("📋 Temp список", callback_data="st:sec:tmp:list"),
            inline_button("🚷 Баны", callback_data="st:sec:bans"),
        ],
        [
            inline_button("🔄 Обновить", callback_data="st:sec"),
            inline_button("◀️ Настройки", callback_data="st:root"),
        ],
    ]
    return inline_keyboard(rows)


async def handle_settings_security(ctx: BotContext, *, message_id: int | None = None) -> None:
    if not await _require_admin_ctx(ctx):
        return
    settings = _get_security(ctx)
    bans = _get_scanner_bans()
    await _send_or_edit(
        ctx,
        _format_security_menu(settings, ban_count=len(bans)),
        markup=_security_keyboard(settings),
        message_id=message_id,
    )


def _apply_security_patch(ctx: BotContext, payload, *, log_details: str):
    from app.routers.security import SecuritySettingsUpdate, update_security

    try:
        if not isinstance(payload, SecuritySettingsUpdate):
            payload = SecuritySettingsUpdate(**payload)
        result = update_security(payload, _make_bot_request(ctx), ctx.db, ctx.user)
        _log_bot_action(ctx, "settings_security_update", log_details)
        return result
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        raise ValueError(detail) from exc


async def _show_temp_list(ctx: BotContext, *, message_id: int | None) -> None:
    settings = _get_security(ctx)
    temp_list = settings.get("temp_whitelist") or []
    if not temp_list:
        await send_message(ctx.bot_token, ctx.chat_id, "Временный whitelist пуст.")
        await handle_settings_security(ctx, message_id=message_id)
        return

    lines = ["⏱ <b>Временный whitelist</b>\n"]
    rows: list[list] = []
    for idx, row in enumerate(temp_list):
        ip = row.get("ip", "?")
        hours = row.get("hours", "?")
        lines.append(f"{idx + 1}. <code>{ip}</code> — {hours} ч.")
        rows.append([inline_button(f"🗑 {ip}", callback_data=f"st:sec:rm:{idx}")])
    rows.append([inline_button("◀️ Назад", callback_data="st:sec")])
    await _send_or_edit(ctx, "\n".join(lines), markup=inline_keyboard(rows), message_id=message_id)


async def _show_scanner_bans(ctx: BotContext, *, message_id: int | None) -> None:
    bans = _get_scanner_bans()
    if not bans:
        await send_message(ctx.bot_token, ctx.chat_id, "Активных банов сканеров нет.")
        await handle_settings_security(ctx, message_id=message_id)
        return

    lines = ["🚷 <b>Баны сканеров</b>\n"]
    rows: list[list] = []
    for idx, ban in enumerate(bans[:10]):
        ip = ban.get("ip", "?")
        lines.append(f"{idx + 1}. <code>{ip}</code>")
        rows.append([inline_button(f"♻️ {ip}", callback_data=f"st:sec:unban:{idx}")])
    rows.append([inline_button("◀️ Назад", callback_data="st:sec")])
    await _send_or_edit(ctx, "\n".join(lines), markup=inline_keyboard(rows), message_id=message_id)


async def handle_security_callback(ctx: BotContext, data: str, *, message_id: int | None) -> None:
    if not await _require_admin_ctx(ctx):
        return

    rest = data[len("st:sec") :].lstrip(":")

    try:
        if rest == "":
            await handle_settings_security(ctx, message_id=message_id)
            return

        if rest.startswith("ip:"):
            enabled = rest.endswith(":1")
            _apply_security_patch(
                ctx,
                {"ip_restriction_enabled": enabled},
                log_details=f"field=ip_restriction_enabled; value={enabled}",
            )
            await handle_settings_security(ctx, message_id=message_id)
            return

        if rest.startswith("scan:"):
            enabled = rest.endswith(":1")
            _apply_security_patch(
                ctx,
                {"block_scanners": enabled},
                log_details=f"field=block_scanners; value={enabled}",
            )
            await handle_settings_security(ctx, message_id=message_id)
            return

        if rest == "ask:allow":
            settings_fsm.set_pending(ctx.telegram_user_id, "sec_allow_ip")
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                "Введите IP или CIDR для постоянного whitelist\n(например <code>192.168.1.0/24</code>):",
                reply_markup={"force_reply": True, "selective": True},
            )
            return

        if rest == "ask:tmp":
            settings_fsm.set_pending(ctx.telegram_user_id, "sec_tmp_ip")
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                "Введите IP для временного whitelist\n(например <code>1.2.3.4</code>):",
                reply_markup={"force_reply": True, "selective": True},
            )
            return

        if rest == "tmp:list":
            await _show_temp_list(ctx, message_id=message_id)
            return

        if rest == "bans":
            await _show_scanner_bans(ctx, message_id=message_id)
            return

        if rest.startswith("tmp:") and rest.split(":", 1)[1].isdigit():
            hours = int(rest.split(":", 1)[1])
            pending = settings_fsm.get_pending(ctx.telegram_user_id)
            if not pending or pending.field != "sec_tmp_ip" or not pending.value:
                await send_message(ctx.bot_token, ctx.chat_id, "Сначала введите IP.")
                return
            ip = pending.value
            settings_fsm.clear_pending(ctx.telegram_user_id)
            from app.routers.security import TempWhitelistRequest, add_temp_whitelist

            add_temp_whitelist(TempWhitelistRequest(ip=ip, hours=hours), _make_bot_request(ctx), ctx.db, ctx.user)
            _log_bot_action(ctx, "settings_security_temp_whitelist", f"ip={ip}; hours={hours}")
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ IP {ip} добавлен на {hours} ч.")
            await handle_settings_security(ctx, message_id=message_id)
            return

        if rest.startswith("rm:"):
            idx = int(rest.split(":", 1)[1]) if rest.split(":", 1)[1].isdigit() else -1
            settings = _get_security(ctx)
            temp_list = settings.get("temp_whitelist") or []
            if idx < 0 or idx >= len(temp_list):
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Запись не найдена.")
                return
            ip = temp_list[idx]["ip"]
            from app.routers.security import remove_temp_whitelist

            remove_temp_whitelist(ip, _make_bot_request(ctx), ctx.db, ctx.user)
            _log_bot_action(ctx, "settings_security_temp_whitelist_remove", f"ip={ip}")
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ IP {ip} удалён из temp whitelist.")
            await _show_temp_list(ctx, message_id=message_id)
            return

        if rest.startswith("unban:"):
            idx = int(rest.split(":", 1)[1]) if rest.split(":", 1)[1].isdigit() else -1
            bans = _get_scanner_bans()
            if idx < 0 or idx >= len(bans):
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Бан не найден.")
                return
            ip = bans[idx].get("ip", "")
            from app.routers.security import UnbanRequest, unban_scanner_ip

            unban_scanner_ip(UnbanRequest(ip=ip))
            _log_bot_action(ctx, "settings_security_unban", f"ip={ip}")
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ IP {ip} разблокирован.")
            await _show_scanner_bans(ctx, message_id=message_id)
            return

    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
        return
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {detail}")
        return


async def handle_security_text(ctx: BotContext, text: str) -> bool:
    pending = settings_fsm.get_pending(ctx.telegram_user_id)
    if pending is None or not pending.field.startswith("sec_"):
        return False

    if not await _require_admin_ctx(ctx):
        settings_fsm.clear_pending(ctx.telegram_user_id)
        return True

    raw = (text or "").strip()
    ip = _validate_ip(raw)
    if not ip:
        await send_message(ctx.bot_token, ctx.chat_id, "Некорректный IP или CIDR.")
        return True

    if pending.field == "sec_allow_ip":
        settings_fsm.clear_pending(ctx.telegram_user_id)
        settings = _get_security(ctx)
        allowed = list(settings.get("allowed_ips") or [])
        if ip in allowed:
            await send_message(ctx.bot_token, ctx.chat_id, f"IP {ip} уже в whitelist.")
        else:
            allowed.append(ip)
            _apply_security_patch(
                ctx,
                {"allowed_ips": allowed},
                log_details=f"field=allowed_ips; add={ip}",
            )
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ IP {ip} добавлен в whitelist.")
        await handle_settings_security(ctx)
        return True

    if pending.field == "sec_tmp_ip":
        settings_fsm.set_pending_value(ctx.telegram_user_id, ip)
        markup = inline_keyboard(
            [
                [
                    inline_button("1 ч.", callback_data="st:sec:tmp:1"),
                    inline_button("12 ч.", callback_data="st:sec:tmp:12"),
                    inline_button("24 ч.", callback_data="st:sec:tmp:24"),
                ],
                [inline_button("❌ Отмена", callback_data="st:sec")],
            ]
        )
        await send_message(
            ctx.bot_token,
            ctx.chat_id,
            f"IP <code>{ip}</code> — выберите срок:",
            reply_markup=markup,
        )
        return True

    return True
