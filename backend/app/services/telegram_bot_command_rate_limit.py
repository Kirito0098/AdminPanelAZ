"""Rate limit for Telegram bot commands (linked users)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.rate_limit.backends import MemoryRateLimitBackend
from app.services.rate_limit.sliding_window import RateLimitExceeded, SlidingWindowLimiter
from app.services.self_service import _get_bounded_int, _set_setting, clamp_int

SETTING_BOT_COMMAND_RATE_MAX = "telegram_bot_command_rate_max"
SETTING_BOT_COMMAND_RATE_WINDOW = "telegram_bot_command_rate_window_seconds"

DEFAULT_BOT_COMMAND_RATE_MAX = 30
DEFAULT_BOT_COMMAND_RATE_WINDOW = 60

BOT_COMMAND_RATE_MAX_BOUNDS = (0, 1000)
BOT_COMMAND_RATE_WINDOW_BOUNDS = (10, 3600)

_BOT_CMD_DETAIL = "Слишком много команд бота. Повторите позже."


def get_bot_command_rate_limits(db: Session) -> dict[str, int]:
    return {
        "max_requests": _get_bounded_int(
            db, SETTING_BOT_COMMAND_RATE_MAX, DEFAULT_BOT_COMMAND_RATE_MAX, BOT_COMMAND_RATE_MAX_BOUNDS
        ),
        "window_seconds": _get_bounded_int(
            db, SETTING_BOT_COMMAND_RATE_WINDOW, DEFAULT_BOT_COMMAND_RATE_WINDOW, BOT_COMMAND_RATE_WINDOW_BOUNDS
        ),
    }


def set_bot_command_rate_limits(
    db: Session,
    *,
    max_requests: int | None = None,
    window_seconds: int | None = None,
) -> dict[str, int]:
    """Store limits (clamped). Caller commits."""
    if max_requests is not None:
        _set_setting(db, SETTING_BOT_COMMAND_RATE_MAX, str(clamp_int(max_requests, BOT_COMMAND_RATE_MAX_BOUNDS)))
    if window_seconds is not None:
        _set_setting(
            db, SETTING_BOT_COMMAND_RATE_WINDOW, str(clamp_int(window_seconds, BOT_COMMAND_RATE_WINDOW_BOUNDS))
        )
    db.flush()
    return get_bot_command_rate_limits(db)


class TelegramBotCommandRateLimitService:
    def __init__(self) -> None:
        self._limiter = SlidingWindowLimiter(MemoryRateLimitBackend())

    def consume(self, db: Session, telegram_user_id: str) -> str | None:
        settings = get_settings()
        if not settings.telegram_bot_command_rate_limit_enabled:
            return None
        limits = get_bot_command_rate_limits(db)
        max_requests = limits["max_requests"]
        if max_requests <= 0:
            return None
        try:
            self._limiter.consume(
                f"tg-bot-cmd:{telegram_user_id}",
                max_requests,
                float(limits["window_seconds"]),
                detail=_BOT_CMD_DETAIL,
            )
        except RateLimitExceeded as exc:
            retry = exc.headers.get("Retry-After", "60")
            return f"Слишком много команд. Повторите через {retry} с."
        return None


telegram_bot_command_rate_limit_service = TelegramBotCommandRateLimitService()
