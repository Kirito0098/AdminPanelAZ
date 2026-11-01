"""Уведомления админам о новых сообщениях абонентов: колокол в панели и карточка в Telegram."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import User, UserMessage, UserRole
from app.services import telegram_api
from app.services.admin_panel_notifications import write_admin_panel_notification
from app.services.app_setting_store import _get_setting
from app.services.user_messages import record_card

logger = logging.getLogger(__name__)

SETTING_BOT_TOKEN = "telegram_bot_token"
PREVIEW_LEN = 120


async def notify_admins_new_message(
    db: Session, *, user: User, message: UserMessage, first_in_thread: bool
) -> None:
    """Колокол на каждое сообщение; карточка в Telegram — только на первое в диалоге.

    `message_id` карточки сохраняем: ответ админа реплаем на неё уходит этому абоненту.
    """
    write_admin_panel_notification(
        db,
        event_type="user_message",
        title=f"{user.username}: новое сообщение",
        message=message.text[:PREVIEW_LEN],
        level="info",
        action_payload={"user_id": user.id},
    )
    if not first_in_thread:
        return
    token = (_get_setting(db, SETTING_BOT_TOKEN, "") or "").strip()
    if not token:
        return
    admins = (
        db.query(User)
        .filter(
            User.role == UserRole.admin,
            User.is_active.is_(True),
            User.telegram_id.isnot(None),
        )
        .all()
    )
    text = (
        f"✉️ {user.username}: новое сообщение\n"
        f"{message.text[:PREVIEW_LEN]}\n\n"
        "Ответить — реплаем на это сообщение или в панели, раздел «Сообщения»."
    )
    for admin in admins:
        chat_id = str(admin.telegram_id)
        result = await telegram_api.call_bot_api(
            token,
            "sendMessage",
            payload={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
            },
        )
        if isinstance(result, dict) and isinstance(result.get("message_id"), int):
            record_card(
                db,
                admin_chat_id=chat_id,
                message_id=int(result["message_id"]),
                user_id=user.id,
            )
