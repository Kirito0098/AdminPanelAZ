"""Telegram bot handler context and shared helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.services.app_setting_store import _get_setting


@dataclass(frozen=True)
class TelegramBotSettingsSnapshot:
    bot_token: str
    interactive_enabled: bool
    bot_username: str
    webhook_set_at: str
    webhook_secret_set: bool
    token_set: bool


def load_telegram_bot_settings_snapshot(db: Session) -> TelegramBotSettingsSnapshot:
    bot_token = _get_setting(db, "telegram_bot_token")
    return TelegramBotSettingsSnapshot(
        bot_token=bot_token,
        interactive_enabled=_get_setting(db, "telegram_bot_interactive_enabled", "false") == "true",
        bot_username=_get_setting(db, "telegram_bot_username"),
        webhook_set_at=_get_setting(db, "telegram_webhook_set_at"),
        webhook_secret_set=bool(_get_setting(db, "telegram_webhook_secret")),
        token_set=bool(bot_token),
    )


@dataclass
class BotContext:
    db: Session
    bot_token: str
    chat_id: int | str
    telegram_user_id: str
    user: User | None
    settings: TelegramBotSettingsSnapshot
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


def inline_button(
    text: str,
    *,
    url: str | None = None,
    callback_data: str | None = None,
    web_app_url: str | None = None,
) -> dict:
    button: dict[str, str | dict[str, str]] = {"text": text}
    if web_app_url:
        button["web_app"] = {"url": web_app_url}
    elif url:
        button["url"] = url
    elif callback_data:
        button["callback_data"] = callback_data
    return button


def reply_button(text: str, *, web_app_url: str | None = None) -> dict:
    button: dict = {"text": text}
    if web_app_url:
        button["web_app"] = {"url": web_app_url}
    return button


def reply_keyboard(
    rows: list[list[dict]],
    *,
    resize: bool = True,
    persistent: bool = True,
    placeholder: str | None = None,
) -> dict:
    markup: dict = {
        "keyboard": rows,
        "resize_keyboard": resize,
        "is_persistent": persistent,
    }
    if placeholder:
        markup["input_field_placeholder"] = placeholder
    return markup
