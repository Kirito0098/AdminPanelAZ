"""One-time link codes for binding telegram_id to panel users."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import User

_LINK_CODES_KEY = "telegram_link_codes"
_CODE_TTL_SECONDS = 600
_CODE_LENGTH = 8


def _load_codes(db: Session) -> dict[str, dict[str, str | int]]:
    from app.routers.maintenance import _get_setting

    raw = _get_setting(db, _LINK_CODES_KEY, "{}")
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_codes(db: Session, codes: dict[str, dict[str, str | int]]) -> None:
    from app.routers.maintenance import _set_setting

    _set_setting(db, _LINK_CODES_KEY, json.dumps(codes))


def _purge_expired(codes: dict[str, dict[str, str | int]]) -> dict[str, dict[str, str | int]]:
    now = datetime.now(timezone.utc)
    kept: dict[str, dict[str, str | int]] = {}
    for code, meta in codes.items():
        expires_raw = str(meta.get("expires_at", ""))
        try:
            expires_at = datetime.fromisoformat(expires_raw)
        except ValueError:
            continue
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > now:
            kept[code] = meta
    return kept


def create_link_code(db: Session, user: User) -> tuple[str, int]:
    codes = _purge_expired(_load_codes(db))
    code = secrets.token_hex(_CODE_LENGTH // 2)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_CODE_TTL_SECONDS)
    codes[code] = {
        "user_id": user.id,
        "expires_at": expires_at.isoformat(),
    }
    _save_codes(db, codes)
    db.commit()
    return code, _CODE_TTL_SECONDS


def redeem_link_code(db: Session, code: str, telegram_id: str) -> tuple[bool, str, User | None]:
    normalized = (code or "").strip().lower()
    if not normalized:
        return False, "Укажите код: /link &lt;код&gt;", None

    codes = _purge_expired(_load_codes(db))
    meta = codes.pop(normalized, None)
    _save_codes(db, codes)

    if not meta:
        db.commit()
        return False, "Код не найден или истёк. Получите новый в панели: Мой профиль.", None

    user_id = int(meta["user_id"])
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.commit()
        return False, "Пользователь панели не найден.", None

    existing = db.query(User).filter(User.telegram_id == telegram_id, User.id != user.id).first()
    if existing:
        db.commit()
        return False, "Этот Telegram ID уже привязан к другому пользователю.", None

    user.telegram_id = telegram_id
    db.commit()
    db.refresh(user)
    return True, f"Аккаунт привязан: <code>{user.username}</code> ({user.role.value})", user
