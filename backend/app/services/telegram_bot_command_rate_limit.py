"""Rate limit for Telegram bot commands (linked users)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.rate_limit.backends import MemoryRateLimitBackend
from app.services.rate_limit.sliding_window import RateLimitExceeded, SlidingWindowLimiter
from app.services.self_service import _get_setting_int

DEFAULT_BOT_COMMAND_RATE_MAX = 30
DEFAULT_BOT_COMMAND_RATE_WINDOW = 60

_BOT_CMD_DETAIL = "Слишком много команд бота. Повторите позже."


class TelegramBotCommandRateLimitService:
    def __init__(self) -> None:
        self._limiter = SlidingWindowLimiter(MemoryRateLimitBackend())

    def consume(self, db: Session, telegram_user_id: str) -> str | None:
        settings = get_settings()
        if not settings.telegram_bot_command_rate_limit_enabled:
            return None
        max_requests = _get_setting_int(db, "telegram_bot_command_rate_max", DEFAULT_BOT_COMMAND_RATE_MAX)
        if max_requests <= 0:
            return None
        window = float(_get_setting_int(db, "telegram_bot_command_rate_window_seconds", DEFAULT_BOT_COMMAND_RATE_WINDOW))
        try:
            self._limiter.consume(
                f"tg-bot-cmd:{telegram_user_id}",
                max_requests,
                window,
                detail=_BOT_CMD_DETAIL,
            )
        except RateLimitExceeded as exc:
            retry = exc.headers.get("Retry-After", "60")
            return f"Слишком много команд. Повторите через {retry} с."
        return None


telegram_bot_command_rate_limit_service = TelegramBotCommandRateLimitService()
