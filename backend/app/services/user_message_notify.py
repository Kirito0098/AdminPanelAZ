"""Уведомления админам о новых сообщениях абонентов: колокол в панели и карточка в Telegram."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import User, UserMessage, UserRole
from app.services.admin_panel_notifications import write_admin_panel_notification
from app.services.app_setting_store import _get_setting
from app.services.telegram import send_tg_message

logger = logging.getLogger(__name__)

SETTING_BOT_TOKEN = "telegram_bot_token"
PREVIEW_LEN = 120


def notify_admins_new_message(
    db: Session, *, user: User, message: UserMessage, first_in_thread: bool
) -> None:
    """Колокол на каждое сообщение; карточка в Telegram — только на первое в диалоге."""
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
        "Ответить — в панели, раздел «Сообщения»."
    )
    for admin in admins:
        send_tg_message(token, str(admin.telegram_id), text)
