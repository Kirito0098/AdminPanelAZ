"""Telegram bot /traffic — fleet summary and top clients by 24h."""

from __future__ import annotations

from app.config import get_settings
from app.services.node_manager import get_active_node
from app.services.self_service import get_owned_client_names
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, is_admin, unlinked_message
from app.services.telegram_bot_handlers.ui import nav_footer_keyboard, send_or_edit
from app.services.traffic.collector import TrafficCollectorService
from app.services.traffic_limit import human_bytes
from app.services import telegram_bot_i18n as i18n

settings = get_settings()
_TOP_LIMIT = 5
_MEDALS = ("🥇", "🥈", "🥉", "4.", "5.")


def _aggregate_clients(rows) -> list[dict]:
    by_key: dict[str, dict] = {}
    for row in rows:
        name = (row.common_name or "").strip()
        if not name:
            continue
        key = name.lower()
        bucket = by_key.get(key)
        if bucket is None:
            bucket = {
                "name": name,
                "traffic_1d": 0,
                "total_bytes": 0,
                "is_active": False,
            }
            by_key[key] = bucket
        bucket["traffic_1d"] += int(row.traffic_1d or 0)
        bucket["total_bytes"] += int(row.total_received or 0) + int(row.total_sent or 0)
        bucket["is_active"] = bucket["is_active"] or bool(row.is_active)
    return list(by_key.values())


def _format_top_lines(clients: list[dict], *, limit: int = _TOP_LIMIT) -> str:
    ranked = sorted(clients, key=lambda item: item["traffic_1d"], reverse=True)[:limit]
    if not ranked or all(item["traffic_1d"] <= 0 for item in ranked):
        return i18n.TRAFFIC_TOP_EMPTY

    lines: list[str] = []
    for index, item in enumerate(ranked):
        if item["traffic_1d"] <= 0:
            break
        medal = _MEDALS[index] if index < len(_MEDALS) else f"{index + 1}."
        status = "🟢" if item["is_active"] else "⚪"
        traffic = human_bytes(item["traffic_1d"]) or "0 B"
        lines.append(
            i18n.TRAFFIC_TOP_LINE.format(
                medal=medal,
                status=status,
                name=item["name"],
                traffic=traffic,
            )
        )
    return "\n".join(lines) if lines else i18n.TRAFFIC_TOP_EMPTY


async def handle_traffic(ctx: BotContext, *, page: int = 0, message_id: int | None = None) -> None:
    del page  # legacy pagination callbacks are ignored

    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    node = get_active_node(ctx.db)
    collector = TrafficCollectorService(ctx.db, node.id)
    rows, _summary = collector.get_summary(set(), settings.traffic_db_stale_seconds)

    if is_admin(ctx.user):
        clients = _aggregate_clients(rows)
        title = i18n.TRAFFIC_FLEET_TITLE
        scope_hint = ""
    else:
        owned_lower = {name.lower() for name in get_owned_client_names(ctx.db, ctx.user, node_id=node.id)}
        if not owned_lower:
            await send_message(ctx.bot_token, ctx.chat_id, i18n.TRAFFIC_NONE)
            return
        clients = _aggregate_clients(
            [row for row in rows if (row.common_name or "").lower() in owned_lower],
        )
        title = i18n.TRAFFIC_USER_TITLE
        scope_hint = i18n.TRAFFIC_USER_SCOPE

    if not clients:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.TRAFFIC_NO_STATS)
        return

    total_1d = sum(item["traffic_1d"] for item in clients)
    total_all = sum(item["total_bytes"] for item in clients)
    active_count = sum(1 for item in clients if item["is_active"])

    text = i18n.TRAFFIC_SUMMARY.format(
        title=title,
        node_name=node.name,
        scope_hint=scope_hint,
        count=len(clients),
        active=active_count,
        traffic_1d=human_bytes(total_1d) or "0 B",
        total_all=human_bytes(total_all) or "0 B",
        top_lines=_format_top_lines(clients),
    )

    markup = nav_footer_keyboard(refresh="nav:traffic")
    await send_or_edit(ctx, text, markup=markup, message_id=message_id)
