"""Telegram bot /nodes — VPN node list and management (admin)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Node, NodeStatus
from app.services.node_manager import (
    check_node_health,
    get_active_node_id,
    node_metadata_dict,
    set_active_node_id,
    sync_local_node,
    update_node_from_health,
)
from app.services.telegram_api import edit_message_text, send_message
from app.services.telegram_bot_handlers.base import (
    BotContext,
    inline_button,
    inline_keyboard,
    is_admin,
    unlinked_message,
)
from app.services import telegram_bot_i18n as i18n

_PAGE_SIZE = 6

_STATUS_ICON = {
    NodeStatus.online: "🟢",
    NodeStatus.offline: "🔴",
    NodeStatus.unknown: "🟡",
}


def _list_nodes(db: Session) -> list[Node]:
    sync_local_node(db)
    return db.query(Node).order_by(Node.is_local.desc(), Node.name).all()


def _format_last_seen(value: datetime | None) -> str:
    if not value:
        return i18n.NODES_NONE
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _node_meta_lines(node: Node) -> list[str]:
    meta = node_metadata_dict(node)
    lines: list[str] = []
    server_ip = meta.get("server_ip")
    if server_ip:
        lines.append(i18n.NODES_LINE_SERVER_IP.format(value=server_ip))
    services_active = meta.get("services_active")
    services_total = meta.get("services_total")
    if isinstance(services_active, int) and isinstance(services_total, int):
        lines.append(i18n.NODES_LINE_SERVICES.format(active=services_active, total=services_total))
    agent_version = meta.get("agent_version")
    if agent_version:
        lines.append(i18n.NODES_LINE_AGENT.format(value=agent_version))
    az_version = meta.get("antizapret_version")
    if az_version:
        lines.append(i18n.NODES_LINE_AZ.format(value=az_version))
    last_error = meta.get("last_error")
    if last_error:
        lines.append(i18n.NODES_LINE_ERROR.format(value=str(last_error)[:200]))
    return lines


def _format_node_card(node: Node, *, active_id: int | None) -> str:
    status = node.status if isinstance(node.status, NodeStatus) else NodeStatus.unknown
    icon = _STATUS_ICON.get(status, "🟡")
    active_mark = i18n.NODES_ACTIVE_MARK if active_id == node.id else ""
    local_mark = i18n.NODES_LOCAL_MARK if node.is_local else ""
    transport = i18n.NODES_TRANSPORT_LOCAL if node.is_local else (
        i18n.NODES_TRANSPORT_MTLS if node.mtls_enabled else i18n.NODES_TRANSPORT_HTTP
    )
    lines = [
        i18n.NODES_CARD.format(
            title=i18n.NODES_CARD_TITLE,
            name=node.name,
            active_mark=active_mark,
            local_mark=local_mark,
            host=node.host,
            port=node.port,
            status_icon=icon,
            status=status.value,
            transport=transport,
            last_seen=_format_last_seen(node.last_seen_at),
        ),
        *_node_meta_lines(node),
    ]
    return "\n".join(lines)


def _list_keyboard(nodes: list[Node], page: int, *, active_id: int | None) -> dict:
    start = page * _PAGE_SIZE
    chunk = nodes[start : start + _PAGE_SIZE]
    rows: list[list[dict]] = []
    for node in chunk:
        status = node.status if isinstance(node.status, NodeStatus) else NodeStatus.unknown
        icon = _STATUS_ICON.get(status, "🟡")
        prefix = "★ " if active_id == node.id else ""
        label = f"{prefix}{icon} {node.name}"
        rows.append([inline_button(label, callback_data=f"nd:{node.id}")])
    nav: list[dict] = []
    if page > 0:
        nav.append(inline_button("◀️", callback_data=f"nodes:{page - 1}"))
    nav.append(inline_button(i18n.BTN_REFRESH, callback_data=f"nodes:{page}"))
    if start + _PAGE_SIZE < len(nodes):
        nav.append(inline_button("▶️", callback_data=f"nodes:{page + 1}"))
    nav.append(inline_button(i18n.BTN_MENU_HOME, callback_data="nav:home"))
    rows.append(nav)
    return inline_keyboard(rows)


def _detail_keyboard(node: Node, *, active_id: int | None) -> dict:
    rows: list[list[dict]] = [
        [inline_button(i18n.BTN_NODES_HEALTH, callback_data=f"ndh:{node.id}")],
    ]
    if active_id != node.id:
        rows.append([inline_button(i18n.BTN_NODES_ACTIVATE, callback_data=f"nda:{node.id}")])
    rows.append([inline_button(i18n.BTN_NODES_BACK, callback_data="nodes:0")])
    return inline_keyboard(rows)


def _get_node(db: Session, node_id: int) -> Node | None:
    return db.query(Node).filter(Node.id == node_id).first()


async def handle_nodes_root(ctx: BotContext, *, page: int = 0, message_id: int | None = None) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return
    if not is_admin(ctx.user):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return

    nodes = _list_nodes(ctx.db)
    if not nodes:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.NODES_EMPTY)
        return

    active_id = get_active_node_id(ctx.db)
    total_pages = max(1, (len(nodes) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    text = i18n.NODES_LIST.format(
        title=i18n.NODES_LIST_TITLE,
        page=page + 1,
        total_pages=total_pages,
        count=len(nodes),
    )
    markup = _list_keyboard(nodes, page, active_id=active_id)
    if message_id is not None:
        await edit_message_text(ctx.bot_token, ctx.chat_id, message_id, text, reply_markup=markup)
    else:
        await send_message(ctx.bot_token, ctx.chat_id, text, reply_markup=markup)


async def handle_node_detail(ctx: BotContext, node_id: int, *, message_id: int | None = None) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return
    if not is_admin(ctx.user):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return

    node = _get_node(ctx.db, node_id)
    if not node:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.NODES_NOT_FOUND)
        return

    active_id = get_active_node_id(ctx.db)
    text = _format_node_card(node, active_id=active_id)
    markup = _detail_keyboard(node, active_id=active_id)
    if message_id is not None:
        await edit_message_text(ctx.bot_token, ctx.chat_id, message_id, text, reply_markup=markup)
    else:
        await send_message(ctx.bot_token, ctx.chat_id, text, reply_markup=markup)


async def handle_node_health(ctx: BotContext, node_id: int, *, message_id: int | None = None) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return
    if not is_admin(ctx.user):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return

    node = _get_node(ctx.db, node_id)
    if not node:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.NODES_NOT_FOUND)
        return

    health = check_node_health(node)
    update_node_from_health(node, health, ctx.db)
    ctx.db.commit()
    ctx.db.refresh(node)
    await handle_node_detail(ctx, node_id, message_id=message_id)


async def handle_node_activate(ctx: BotContext, node_id: int, *, message_id: int | None = None) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return
    if not is_admin(ctx.user):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return

    node = _get_node(ctx.db, node_id)
    if not node:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.NODES_NOT_FOUND)
        return

    set_active_node_id(ctx.db, node.id)
    ctx.db.commit()
    health = check_node_health(node)
    update_node_from_health(node, health, ctx.db)
    ctx.db.commit()
    ctx.db.refresh(node)

    from app.config import get_settings
    from app.services.action_log import log_action

    settings = get_settings()
    if settings.audit_log_enabled and ctx.user:
        log_action(
            ctx.db,
            action="node_activate",
            user_id=ctx.user.id,
            username=ctx.user.username,
            remote_addr="telegram",
            details=f"name={node.name}, id={node.id}",
        )

    await handle_node_detail(ctx, node_id, message_id=message_id)
