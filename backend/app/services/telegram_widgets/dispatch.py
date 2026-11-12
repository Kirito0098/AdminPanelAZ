"""Маршрутизация ``widget_query``: находим карточку по сообщению и отдаём её типу."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.models import TelegramWidget
from app.services.telegram_api import answer_widget_query
from app.services.telegram_widgets import access_request, hub

logger = logging.getLogger(__name__)


def _query_identity(query: dict) -> tuple[str, str, int] | None:
    """Личка, chat.id == from.id — та же политика, что у message/callback."""
    from_user = query.get("from") or {}
    chat = query.get("chat") or {}
    if chat.get("type") != "private":
        return None
    telegram_id = str(from_user.get("id") or "")
    chat_id = str(chat.get("id") or "")
    if not telegram_id or not chat_id or chat_id != telegram_id:
        return None
    try:
        message_id = int(query.get("message_id"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return chat_id, telegram_id, message_id


def resolve_card(db: Session, query: dict) -> TelegramWidget | None:
    """Карточка по ``(chat_id, message_id)``; чужая не подтверждается."""
    identity = _query_identity(query)
    if identity is None:
        return None
    chat_id, telegram_id, message_id = identity
    row = (
        db.query(TelegramWidget)
        .filter(
            TelegramWidget.chat_id == chat_id,
            TelegramWidget.message_id == message_id,
        )
        .first()
    )
    if row is None or str(row.telegram_id) != telegram_id:
        return None
    return row


async def handle_widget_query(
    db: Session,
    query: dict,
    *,
    bot_token: str,
    mini_app_url: str = "",
) -> None:
    """Точка входа из ``TelegramBotService.handle_update``."""
    query_id = str(query.get("id") or "")
    if not query_id:
        return
    row = resolve_card(db, query)
    if row is None:
        if bot_token:
            await answer_widget_query(bot_token, query_id)
        return
    try:
        if row.kind == access_request.KIND_ACCESS_REQUEST:
            await access_request.handle_query(db, row, query, bot_token=bot_token)
        elif row.kind == hub.KIND_HUB:
            await hub.handle_query(
                db, row, query, bot_token=bot_token, mini_app_url=mini_app_url
            )
        else:
            logger.warning("telegram widgets: unknown kind %r", row.kind)
            if bot_token:
                await answer_widget_query(bot_token, query_id)
    except Exception:  # noqa: BLE001 — виджет не должен ронять обработку апдейтов
        logger.exception("telegram widgets: query handling failed")
        if bot_token:
            await answer_widget_query(
                bot_token, query_id, data=json.dumps({"e": "error"}, separators=(",", ":"))
            )
