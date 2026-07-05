"""Parse and resolve Telegram chat / notify recipient lists."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import User


def parse_chat_ids(raw: str) -> list[str]:
    value = (raw or "").strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            data = json.loads(value)
            if isinstance(data, list):
                return _unique_str_list(str(item).strip() for item in data if str(item).strip())
        except json.JSONDecodeError:
            pass
    return _unique_str_list(part.strip() for part in value.split(",") if part.strip())


def join_chat_ids(chat_ids: list[str]) -> str:
    return ",".join(_unique_str_list(item.strip() for item in chat_ids if item.strip()))


def parse_user_ids(raw: str) -> list[int]:
    value = (raw or "").strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            data = json.loads(value)
            if isinstance(data, list):
                return _unique_int_list(int(item) for item in data)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return _unique_int_list(int(part.strip()) for part in value.split(",") if part.strip().isdigit())


def join_user_ids(user_ids: list[int]) -> str:
    return json.dumps(_unique_int_list(user_ids), separators=(",", ":"))


def _unique_str_list(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _unique_int_list(values) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for item in values:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def get_setting_chat_ids(get_setting) -> list[str]:
    return parse_chat_ids(get_setting("telegram_chat_id"))


def get_notify_recipient_user_ids(get_setting) -> list[int] | None:
    raw = get_setting("telegram_notify_recipient_user_ids", "")
    if not raw.strip():
        return None
    ids = parse_user_ids(raw)
    return ids or None


def filter_notify_recipients(db: Session, users: list[User], get_setting) -> list[User]:
    allowed_ids = get_notify_recipient_user_ids(get_setting)
    if allowed_ids is None:
        return users
    allowed = set(allowed_ids)
    return [user for user in users if user.id in allowed]


def resolve_notify_recipient_users(db: Session, get_setting) -> list[User]:
    from app.models import User as UserModel

    users = db.query(UserModel).filter(UserModel.telegram_id.isnot(None)).all()
    users = [user for user in users if (user.telegram_id or "").strip()]
    return filter_notify_recipients(db, users, get_setting)
