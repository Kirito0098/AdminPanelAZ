"""Telegram bot handler context and shared helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import User, UserRole


@dataclass
class BotContext:
    db: Session
    bot_token: str
    chat_id: int | str
    telegram_user_id: str
    user: User | None
    mini_app_url: str = ""


def resolve_user(db: Session, telegram_user_id: str) -> User | None:
    tg_id = str(telegram_user_id or "").strip()
    if not tg_id:
        return None
    return db.query(User).filter(User.telegram_id == tg_id, User.is_active.is_(True)).first()


def is_admin(user: User | None) -> bool:
    return user is not None and user.role == UserRole.admin


def unlinked_message() -> str:
    from app.services import telegram_bot_i18n as i18n

    return i18n.UNLINKED


def inline_keyboard(rows: list[list[dict]]) -> dict:
    return {"inline_keyboard": rows}


def inline_button(text: str, *, url: str | None = None, callback_data: str | None = None) -> dict:
    button: dict[str, str] = {"text": text}
    if url:
        button["url"] = url
    elif callback_data:
        button["callback_data"] = callback_data
    return button
