"""Telegram bot /settings → Maintenance section (Phase 3)."""

from __future__ import annotations

import json

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.models import Node, NodeStatus
from app.services.node_manager import _is_vpn_node
from app.routers.maintenance import cancel_server_reboot, schedule_server_reboot
from app.schemas import ServerRebootRequest, ServiceRestartRequest
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard
from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers.nodes import _list_nodes
from app.services.telegram_bot_handlers.settings import (
    _log_bot_action,
    _make_bot_request,
    _require_admin_ctx,
    _send_or_edit,
)

_REBOOT_STATUS_ICON = {
    NodeStatus.online: "🟢",
    NodeStatus.offline: "🔴",
    NodeStatus.unknown: "🟡",
}

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
            [inline_button("🔁 Перезагрузка сервера", callback_data="st:mnt:reboot")],
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


def _get_node(db, node_id: int) -> Node | None:
    return db.query(Node).filter(Node.id == node_id).first()


def _reboot_nodes_keyboard(nodes: list[Node]) -> dict:
    rows: list[list] = []
    for node in nodes:
        status = node.status if isinstance(node.status, NodeStatus) else NodeStatus.unknown
        icon = _REBOOT_STATUS_ICON.get(status, "🟡")
        rows.append([inline_button(f"{icon} {node.name}", callback_data=f"st:mnt:reboot:n:{node.id}")])
    rows.append([inline_button("◀️ Назад", callback_data="st:mnt")])
    return inline_keyboard(rows)


async def _show_reboot_nodes(ctx: BotContext, *, message_id: int | None = None) -> None:
    nodes = [n for n in _list_nodes(ctx.db) if _is_vpn_node(n)]
    if not nodes:
        await send_message(ctx.bot_token, ctx.chat_id, "❌ Нет доступных узлов.")
        return
    await _send_or_edit(
        ctx,
        "🔁 <b>Перезагрузка сервера ОС</b>\n\nВыберите узел:",
        markup=_reboot_nodes_keyboard(nodes),
        message_id=message_id,
    )


async def _show_reboot_confirm(ctx: BotContext, node_id: int, *, message_id: int | None = None) -> None:
    node = _get_node(ctx.db, node_id)
    if not node:
        await send_message(ctx.bot_token, ctx.chat_id, "❌ Узел не найден.")
        return
    markup = inline_keyboard(
        [
            [
                inline_button("✅ Да", callback_data=f"st:mnt:reboot:ask:{node_id}"),
                inline_button("❌ Отмена", callback_data="st:mnt"),
            ]
        ]
    )
    await _send_or_edit(
        ctx,
        f"⚠️ Точно перезагрузить <b>{node.name}</b>?\nПерезагрузка ОС сервера.",
        markup=markup,
        message_id=message_id,
    )


async def handle_maintenance_text(ctx: BotContext, text: str) -> bool:
    pending = settings_fsm.get_pending(ctx.telegram_user_id)
    if pending is None or pending.field != "mnt_reboot":
        return False

    if not await _require_admin_ctx(ctx):
        settings_fsm.clear_pending(ctx.telegram_user_id)
        return True

    raw = (text or "").strip()
    if raw != "REBOOT":
        await send_message(ctx.bot_token, ctx.chat_id, "Введите <code>REBOOT</code> для подтверждения.")
        return True

    node_id_raw = pending.value
    if not node_id_raw or not node_id_raw.isdigit():
        settings_fsm.clear_pending(ctx.telegram_user_id)
        await send_message(ctx.bot_token, ctx.chat_id, "❌ Узел не выбран.")
        return True

    node_id = int(node_id_raw)
    settings_fsm.clear_pending(ctx.telegram_user_id)

    try:
        result = schedule_server_reboot(
            ServerRebootRequest(node_id=node_id, confirm="REBOOT"),
            _make_bot_request(ctx),
            ctx.db,
            ctx.user,
        )
        _log_bot_action(
            ctx,
            "settings_reboot_schedule",
            f"node_id={node_id}; reboot_id={result.reboot_id}",
        )
        warning = f"\n⚠️ {result.warning}" if result.warning else ""
        markup = inline_keyboard(
            [[inline_button("❌ Отменить", callback_data=f"st:mnt:reboot:cancel:{result.reboot_id}")]]
        )
        await send_message(
            ctx.bot_token,
            ctx.chat_id,
            f"✅ Перезагрузка <b>{result.node_name}</b> через {result.delay_seconds} с.{warning}\n"
            f"Выполнение: <code>{result.execute_at.isoformat()}</code>",
            reply_markup=markup,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {detail}")
    return True


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

        if rest == "reboot":
            await _show_reboot_nodes(ctx, message_id=message_id)
            return

        if rest.startswith("reboot:n:"):
            node_id_raw = rest.split(":", 2)[2]
            if not node_id_raw.isdigit():
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Некорректный узел.")
                return
            await _show_reboot_confirm(ctx, int(node_id_raw), message_id=message_id)
            return

        if rest.startswith("reboot:ask:"):
            node_id_raw = rest.split(":", 2)[2]
            if not node_id_raw.isdigit():
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Некорректный узел.")
                return
            node = _get_node(ctx.db, int(node_id_raw))
            if not node:
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Узел не найден.")
                return
            settings_fsm.set_pending(ctx.telegram_user_id, "mnt_reboot")
            settings_fsm.set_pending_value(ctx.telegram_user_id, node_id_raw)
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                f"Отправьте <code>REBOOT</code> для подтверждения перезагрузки <b>{node.name}</b>.",
                reply_markup={"force_reply": True, "selective": True},
            )
            return

        if rest.startswith("reboot:cancel:"):
            reboot_id = rest.split(":", 2)[2]
            if not reboot_id:
                await send_message(ctx.bot_token, ctx.chat_id, "❌ Некорректный идентификатор.")
                return
            result = cancel_server_reboot(reboot_id, _make_bot_request(ctx), ctx.db, ctx.user)
            _log_bot_action(
                ctx,
                "settings_reboot_cancel",
                f"node_id={result.node_id}; reboot_id={reboot_id}",
            )
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                f"✅ Перезагрузка <b>{result.node_name}</b> отменена.",
            )
            return

    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
        return
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {detail}")
        return
