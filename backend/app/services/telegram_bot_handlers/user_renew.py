"""Bound-user Telegram flow: redeem unlock code («Продлить по ключу»)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.services.telegram_api import send_message
from app.services.unlock_codes import redeem_unlock_code_for_user
from app.services.unlock_redeem_rate_limit import unlock_redeem_rate_limit_service

# In-memory FSM: telegram_id -> awaiting code
_awaiting_code: set[str] = set()


async def start_redeem_prompt(bot_token: str, chat_id: str) -> None:
    _awaiting_code.add(str(chat_id))
    await send_message(bot_token, chat_id, "Отправьте unlock-ключ одним сообщением.")


async def try_handle_code_message(
    db: Session, bot_token: str, *, telegram_id: str, text: str
) -> bool:
    """If user is in redeem FSM, consume message. Returns True if handled."""
    tid = str(telegram_id)
    if tid not in _awaiting_code:
        return False
    _awaiting_code.discard(tid)
    limited = unlock_redeem_rate_limit_service.consume(tid)
    if limited:
        await send_message(bot_token, tid, limited)
        return True
    user = (
        db.query(User)
        .filter(User.telegram_id == tid, User.role == UserRole.user, User.is_active.is_(True))
        .first()
    )
    if user is None:
        await send_message(bot_token, tid, "Аккаунт не найден.")
        return True
    try:
        result = redeem_unlock_code_for_user(db, code=text.strip(), user=user)
        days = result.get("grant_days") or 0
        await send_message(bot_token, tid, f"Ключ принят. Доступ продлён на {days} дн.")
    except ValueError as exc:
        await send_message(bot_token, tid, str(exc))
    return True
