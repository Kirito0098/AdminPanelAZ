"""Telegram bot /traffic command for linked users."""

from __future__ import annotations

from app.config import get_settings
from app.services.node_manager import get_active_node
from app.services.self_service import get_owned_client_names
from app.services.telegram_api import send_message
from app.services.telegram_bot_data import list_user_configs
from app.services.telegram_bot_handlers.base import BotContext, unlinked_message
from app.services.telegram_bot_handlers.ui import nav_footer_keyboard, send_or_edit
from app.services.traffic.collector import TrafficCollectorService
from app.services.traffic_limit import human_bytes
from app.services import telegram_bot_i18n as i18n

settings = get_settings()
_PAGE_SIZE = 10


def _format_row_line(name: str, received: int, sent: int, is_active: bool) -> str:
    total = human_bytes(received + sent) or "0 B"
    status = "🟢" if is_active else "⚪"
    return f"{status} <code>{name}</code> — {total}"


async def handle_traffic(ctx: BotContext, *, page: int = 0, message_id: int | None = None) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    node = get_active_node(ctx.db)
    owned = get_owned_client_names(ctx.db, ctx.user, node_id=node.id)
    if not owned:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.TRAFFIC_NONE)
        return

    collector = TrafficCollectorService(ctx.db, node.id)
    rows, summary = collector.get_summary(set(), settings.traffic_db_stale_seconds)
    rows = [row for row in rows if row.common_name in owned]
    rows.sort(key=lambda r: r.common_name.lower())

    if not rows:
        configs = list_user_configs(ctx.db, ctx.user)
        names = ", ".join(c.client_name for c in configs[:5])
        extra = f"\n\nВаши клиенты: {names}" if names else ""
        await send_message(ctx.bot_token, ctx.chat_id, i18n.TRAFFIC_NO_STATS + extra)
        return

    total_pages = max(1, (len(rows) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * _PAGE_SIZE : page * _PAGE_SIZE + _PAGE_SIZE]
    lines = [_format_row_line(r.common_name, r.total_received, r.total_sent, r.is_active) for r in chunk]
    total_human = human_bytes(summary.total_received + summary.total_sent) or "0 B"
    text = i18n.TRAFFIC_LIST.format(
        page=page + 1,
        total_pages=total_pages,
        count=len(rows),
        total=total_human,
        lines="\n".join(lines),
    )

    nav: list = []
    if page > 0:
        nav.append({"text": "◀️", "callback_data": f"traffic:{page - 1}"})
    if (page + 1) * _PAGE_SIZE < len(rows):
        nav.append({"text": "▶️", "callback_data": f"traffic:{page + 1}"})
    extra_rows: list[list] = []
    if nav:
        from app.services.telegram_bot_handlers.base import inline_button

        extra_rows.append([inline_button(b["text"], callback_data=b["callback_data"]) for b in nav])

    markup = nav_footer_keyboard(refresh="nav:traffic", extra_rows=extra_rows)
    await send_or_edit(ctx, text, markup=markup, message_id=message_id)
