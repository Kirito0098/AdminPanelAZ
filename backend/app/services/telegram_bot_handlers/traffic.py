"""Telegram bot /traffic — fleet summary and top clients by 24h."""

from __future__ import annotations

from html import escape

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node, User
from app.services.node_manager import get_active_node
from app.services.config_access import accessible_client_names
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, is_admin, unlinked_message
from app.services.telegram_bot_handlers.ui import nav_footer_keyboard, send_or_edit
from app.services.traffic.active_clients import live_active_names_for_node
from app.services.traffic.collector import TrafficCollectorService
from app.services.traffic.period import resolve_traffic_period
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
        bucket["traffic_1d"] += int(row.traffic_period or 0)
        bucket["total_bytes"] += int(row.total_received or 0) + int(row.total_sent or 0)
        bucket["is_active"] = bucket["is_active"] or bool(row.is_active)
    return list(by_key.values())


def _format_top_lines(top: list[dict], *, limit: int = _TOP_LIMIT) -> str:
    ranked = top[:limit]
    if not ranked:
        return i18n.TRAFFIC_TOP_EMPTY

    lines: list[str] = []
    for index, item in enumerate(ranked):
        medal = _MEDALS[index] if index < len(_MEDALS) else f"{index + 1}."
        status = "🟢" if item["active"] else "⚪"
        lines.append(
            i18n.TRAFFIC_TOP_LINE.format(
                medal=medal,
                status=status,
                name=escape(str(item["name"])),
                traffic=item["traffic"],
            )
        )
    return "\n".join(lines) if lines else i18n.TRAFFIC_TOP_EMPTY


def collect_traffic(db: Session, user: User) -> tuple[list[dict], Node, str]:
    """Агрегированные клиенты + узел. ``reason``: ``none`` | ``nostats`` | ``""``."""

    node = get_active_node(db)
    collector = TrafficCollectorService(db, node.id)
    active_names = live_active_names_for_node(db, node)
    window = resolve_traffic_period(
        period="1d",
        from_s=None,
        to_s=None,
        retention_days=settings.traffic_sample_retention_days,
        tz_name="UTC",
    )
    rows, _summary = collector.get_summary(
        active_names, settings.traffic_db_stale_seconds, period_window=window
    )

    if is_admin(user):
        return _aggregate_clients(rows), node, ""

    allowed = accessible_client_names(db, user, node_id=node.id) or set()
    owned_lower = {name.lower() for name in allowed}
    if not owned_lower:
        return [], node, "none"
    clients = _aggregate_clients(
        [row for row in rows if (row.common_name or "").lower() in owned_lower],
    )
    return clients, node, ("" if clients else "nostats")


def traffic_by_client(db: Session, user: User) -> dict[str, int]:
    """Трафик за сутки по имени клиента (нижний регистр), для карточки конфигов."""
    clients, _node, _reason = collect_traffic(db, user)
    return {str(item["name"]).lower(): int(item["traffic_1d"]) for item in clients}


def traffic_snapshot(
    db: Session,
    user: User,
    *,
    top_limit: int = _TOP_LIMIT,
) -> tuple[dict | None, str]:
    """Сводка трафика для экрана и виджета. ``reason``: ``none`` | ``nostats``."""

    clients, node, reason = collect_traffic(db, user)
    if reason == "none":
        return None, "none"
    if not clients:
        return None, "nostats"

    if is_admin(user):
        title = i18n.TRAFFIC_FLEET_TITLE
        scope_hint = ""
    else:
        title = i18n.TRAFFIC_USER_TITLE
        scope_hint = i18n.TRAFFIC_USER_SCOPE

    ranked = [
        {
            "name": str(item["name"]),
            "traffic": human_bytes(item["traffic_1d"]) or "0 B",
            "active": bool(item["is_active"]),
        }
        for item in sorted(clients, key=lambda item: item["traffic_1d"], reverse=True)
        if item["traffic_1d"] > 0
    ][:top_limit]

    return (
        {
            "title": title,
            "scope_hint": scope_hint,
            "node": str(node.name or ""),
            "count": len(clients),
            "active": sum(1 for item in clients if item["is_active"]),
            "traffic_1d": human_bytes(sum(item["traffic_1d"] for item in clients)) or "0 B",
            "total_all": human_bytes(sum(item["total_bytes"] for item in clients)) or "0 B",
            "top": ranked,
        },
        "",
    )


async def handle_traffic(ctx: BotContext, *, page: int = 0, message_id: int | None = None) -> None:
    del page  # legacy pagination callbacks are ignored

    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    snapshot, reason = traffic_snapshot(ctx.db, ctx.user)
    if snapshot is None:
        await send_message(
            ctx.bot_token,
            ctx.chat_id,
            i18n.TRAFFIC_NONE if reason == "none" else i18n.TRAFFIC_NO_STATS,
        )
        return

    text = i18n.TRAFFIC_SUMMARY.format(
        title=snapshot["title"],
        node_name=escape(snapshot["node"]),
        scope_hint=snapshot["scope_hint"],
        count=snapshot["count"],
        active=snapshot["active"],
        traffic_1d=snapshot["traffic_1d"],
        total_all=snapshot["total_all"],
        top_lines=_format_top_lines(snapshot["top"]),
    )

    markup = nav_footer_keyboard(refresh="nav:traffic")
    await send_or_edit(ctx, text, markup=markup, message_id=message_id)
