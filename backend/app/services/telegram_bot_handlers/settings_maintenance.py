"""Telegram bot /settings → Maintenance section (Phase 3)."""

from __future__ import annotations

import json

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.schemas import ServiceRestartRequest
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard
from app.services.telegram_bot_handlers.settings import (
    _log_bot_action,
    _make_bot_request,
    _require_admin_ctx,
    _send_or_edit,
)

VPN_SERVICES = (
    "openvpn-server@antizapret-udp",
    "openvpn-server@antizapret-tcp",
    "openvpn-server@vpn-udp",
    "openvpn-server@vpn-tcp",
    "wg-quick@antizapret",
    "wg-quick@vpn",
)


def _antizapret_path(ctx: BotContext) -> str:
    from app.services.node_manager import get_node_antizapret_path

    return str(get_node_antizapret_path(ctx.db))


def _format_maintenance_menu(ctx: BotContext) -> str:
    path = _antizapret_path(ctx)
    return (
        "🔧 <b>Обслуживание</b>\n\n"
        f"AntiZapret path:\n<code>{path}</code>\n\n"
        "Опасные операции требуют подтверждения."
    )


def _maintenance_keyboard() -> dict:
    return inline_keyboard(
        [
            [inline_button("▶️ doall.sh", callback_data="st:mnt:cfrm:doall")],
            [inline_button("♻️ Пересоздать профили", callback_data="st:mnt:cfrm:recreate")],
            [inline_button("🔄 Перезапуск службы", callback_data="st:mnt:svc")],
            [
                inline_button("🔄 Обновить", callback_data="st:mnt"),
                inline_button("◀️ Настройки", callback_data="st:root"),
            ],
        ]
    )


def _service_keyboard() -> dict:
    rows: list[list] = []
    for idx, name in enumerate(VPN_SERVICES):
        short = name.replace("openvpn-server@", "ovpn:").replace("wg-quick@", "wg:")
        if idx % 2 == 0:
            rows.append([])
        rows[-1].append(inline_button(short, callback_data=f"st:mnt:cfrm:rst:{idx}"))
    rows.append([inline_button("◀️ Назад", callback_data="st:mnt")])
    return inline_keyboard(rows)


async def handle_settings_maintenance(ctx: BotContext, *, message_id: int | None = None) -> None:
    if not await _require_admin_ctx(ctx):
        return
    await _send_or_edit(
        ctx,
        _format_maintenance_menu(ctx),
        markup=_maintenance_keyboard(),
        message_id=message_id,
    )


async def handle_maintenance_callback(ctx: BotContext, data: str, *, message_id: int | None) -> None:
    if not await _require_admin_ctx(ctx):
        return

    rest = data[len("st:mnt") :].lstrip(":")

    try:
        if rest == "":
            await handle_settings_maintenance(ctx, message_id=message_id)
            return

        if rest == "svc":
            await _send_or_edit(
                ctx,
                "🔄 <b>Перезапуск службы VPN</b>\n\nВыберите службу:",
                markup=_service_keyboard(),
                message_id=message_id,
            )
            return

        if rest == "cfrm:doall":
            markup = inline_keyboard(
                [
                    [
                        inline_button("✅ Запустить", callback_data="st:mnt:do:doall"),
                        inline_button("❌ Отмена", callback_data="st:mnt"),
                    ]
                ]
            )
            await _send_or_edit(
                ctx,
                "⚠️ Запустить <b>doall.sh</b>?\nОперация может занять несколько минут.",
                markup=markup,
                message_id=message_id,
            )
            return

        if rest == "do:doall":
            from app.routers.maintenance import run_doall

            result = run_doall(_make_bot_request(ctx), ctx.db, ctx.user)
            if isinstance(result, JSONResponse):
                body = json.loads(result.body.decode())
                detail = body.get("detail", "doall уже выполняется")
                await send_message(ctx.bot_token, ctx.chat_id, f"❌ {detail}")
                return
            _log_bot_action(ctx, "settings_run_doall", "action=doall")
            message = result.get("message", "doall поставлен в очередь")
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ {message}")
            return

        if rest == "cfrm:recreate":
            markup = inline_keyboard(
                [
                    [
                        inline_button("✅ Пересоздать", callback_data="st:mnt:do:recreate"),
                        inline_button("❌ Отмена", callback_data="st:mnt"),
                    ]
                ]
            )
            await _send_or_edit(
                ctx,
                "⚠️ Пересоздать профили клиентов?\nМожет затронуть активные подключения.",
                markup=markup,
                message_id=message_id,
            )
            return

        if rest == "do:recreate":
            from app.routers.settings import recreate_profiles

            result = recreate_profiles(_make_bot_request(ctx), ctx.db, ctx.user)
            _log_bot_action(ctx, "settings_recreate_profiles", "action=recreate_profiles")
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ {result.message}")
            return

        if rest.startswith("cfrm:rst:"):
            idx = int(rest.split(":", 2)[2]) if rest.split(":", 2)[2].isdigit() else -1
            if idx < 0 or idx >= len(VPN_SERVICES):
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Неизвестная служба.")
                return
            service = VPN_SERVICES[idx]
            markup = inline_keyboard(
                [
                    [
                        inline_button("✅ Перезапустить", callback_data=f"st:mnt:do:rst:{idx}"),
                        inline_button("❌ Отмена", callback_data="st:mnt:svc"),
                    ]
                ]
            )
            await _send_or_edit(
                ctx,
                "⚠️ <b>Перезапустить службу?</b>\n"
                f"<code>{service}</code>\n\n"
                "Активные VPN-сессии будут прерваны.",
                markup=markup,
                message_id=message_id,
            )
            return

        if rest.startswith("do:rst:"):
            idx = int(rest.split(":", 2)[2]) if rest.split(":", 2)[2].isdigit() else -1
            if idx < 0 or idx >= len(VPN_SERVICES):
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Неизвестная служба.")
                return
            service = VPN_SERVICES[idx]
            from app.routers.maintenance import restart_service

            result = restart_service(
                ServiceRestartRequest(service_name=service),
                _make_bot_request(ctx),
                ctx.db,
                ctx.user,
            )
            _log_bot_action(ctx, "settings_restart_service", f"service={service}")
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ {result.message}")
            return

    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
        return
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {detail}")
        return
