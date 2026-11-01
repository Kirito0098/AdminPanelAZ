"""Чат абонент ↔ администратор: запись, чтение, счётчики, режим переписки и доставка."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User, UserMessage
from app.services.app_setting_store import _get_setting
from app.services.telegram import send_tg_message_result

logger = logging.getLogger(__name__)

MESSAGE_MAX_LEN = 4096
SETTING_BOT_TOKEN = "telegram_bot_token"
DIRECTION_IN = "in"
DIRECTION_OUT = "out"
REPLY_PREFIX = "Сообщение от администратора:"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def in_chat_mode(user: User) -> bool:
    return user.chat_mode_since is not None


def enter_chat_mode(db: Session, user: User) -> None:
    user.chat_mode_since = _now()
    db.add(user)
    db.commit()


def leave_chat_mode(db: Session, user: User) -> None:
    if user.chat_mode_since is None:
        return
    user.chat_mode_since = None
    db.add(user)
    db.commit()


def record_inbound(
    db: Session, *, user: User, text: str, telegram_message_id: int | None
) -> UserMessage | None:
    """Сохранить сообщение абонента; None — повторная доставка того же апдейта."""
    message = UserMessage(
        user_id=user.id,
        direction=DIRECTION_IN,
        text=text[:MESSAGE_MAX_LEN],
        telegram_message_id=telegram_message_id,
    )
    db.add(message)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("duplicate telegram message %s for user_id=%s", telegram_message_id, user.id)
        return None
    db.refresh(message)
    return message


def deliver_to_user(db: Session, *, user: User, text: str) -> tuple[bool, str | None]:
    """Best-effort доставка: сообщение уже сохранено, ошибка не отменяет запись."""
    if not user.telegram_id:
        return False, "у абонента не привязан Telegram"
    token = (_get_setting(db, SETTING_BOT_TOKEN, "") or "").strip()
    if not token:
        return False, "не задан токен бота"
    ok, code = send_tg_message_result(token, str(user.telegram_id), f"{REPLY_PREFIX}\n{text}")
    if ok:
        return True, None
    if code == 403:
        return False, "бот заблокирован абонентом"
    if code is None:
        return False, "модуль Telegram выключен"
    return False, f"Telegram вернул ошибку {code}"


def send_admin_reply(
    db: Session, *, user: User, admin: User, text: str
) -> tuple[UserMessage, bool, str | None]:
    message = UserMessage(
        user_id=user.id, direction=DIRECTION_OUT, admin_id=admin.id, text=text
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    delivered, warning = deliver_to_user(db, user=user, text=text)
    return message, delivered, warning


def list_messages(
    db: Session, *, user_id: int, limit: int = 50, before_id: int | None = None
) -> list[UserMessage]:
    query = db.query(UserMessage).filter(UserMessage.user_id == user_id)
    if before_id is not None:
        query = query.filter(UserMessage.id < before_id)
    rows = query.order_by(UserMessage.id.desc()).limit(limit).all()
    return list(reversed(rows))


def list_threads(
    db: Session,
    *,
    query: str | None = None,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    unread = (
        db.query(
            UserMessage.user_id.label("user_id"),
            func.count(UserMessage.id).label("unread_count"),
        )
        .filter(
            UserMessage.direction == DIRECTION_IN,
            UserMessage.read_by_admin_at.is_(None),
        )
        .group_by(UserMessage.user_id)
        .subquery()
    )
    last_ids = (
        db.query(
            UserMessage.user_id.label("user_id"),
            func.max(UserMessage.id).label("last_id"),
        )
        .group_by(UserMessage.user_id)
        .subquery()
    )
    rows = (
        db.query(User, UserMessage, unread.c.unread_count)
        .join(last_ids, last_ids.c.user_id == User.id)
        .join(UserMessage, UserMessage.id == last_ids.c.last_id)
        .outerjoin(unread, unread.c.user_id == User.id)
        .order_by(UserMessage.id.desc())
    )
    if query:
        rows = rows.filter(User.username.ilike(f"%{query}%"))
    if unread_only:
        rows = rows.filter(func.coalesce(unread.c.unread_count, 0) > 0)
    return [
        {
            "user_id": user.id,
            "username": user.username,
            "last_text": message.text,
            "last_at": message.created_at,
            "last_direction": message.direction,
            "unread_count": int(unread_count or 0),
        }
        for user, message, unread_count in rows.offset(offset).limit(limit).all()
    ]


def mark_read(db: Session, *, user_id: int) -> int:
    updated = (
        db.query(UserMessage)
        .filter(
            UserMessage.user_id == user_id,
            UserMessage.direction == DIRECTION_IN,
            UserMessage.read_by_admin_at.is_(None),
        )
        .update({UserMessage.read_by_admin_at: _now()}, synchronize_session=False)
    )
    db.commit()
    return int(updated or 0)


def unread_for_user(db: Session, *, user_id: int) -> int:
    count = (
        db.query(func.count(UserMessage.id))
        .filter(
            UserMessage.user_id == user_id,
            UserMessage.direction == DIRECTION_IN,
            UserMessage.read_by_admin_at.is_(None),
        )
        .scalar()
    )
    return int(count or 0)


def unread_total(db: Session) -> int:
    count = (
        db.query(func.count(UserMessage.id))
        .filter(
            UserMessage.direction == DIRECTION_IN,
            UserMessage.read_by_admin_at.is_(None),
        )
        .scalar()
    )
    return int(count or 0)
