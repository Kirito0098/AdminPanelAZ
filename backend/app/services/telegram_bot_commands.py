"""Per-role Telegram command lists.

Telegram has no role scopes: the default list serves everyone (users and
unlinked), and each linked admin additionally gets a ``chat`` scope with the
admin commands. Re-synced whenever the bot settings are saved.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.services import telegram_bot_i18n as i18n
from app.services.feature_guards import get_feature_service
from app.services.telegram_api import set_my_commands_sync

logger = logging.getLogger(__name__)

# Команда → фича, без которой её не показываем в меню Telegram.
FEATURE_BY_COMMAND: dict[str, str] = {
    "unlock": "unlock_codes",
    "cidr": "routing",
    "warper": "warper",
    "awg2": "awg2",
}


def _command_enabled(command: str) -> bool:
    feature = FEATURE_BY_COMMAND.get(command)
    if feature is None:
        return True
    try:
        return get_feature_service().is_enabled(feature)
    except Exception:  # noqa: BLE001 — меню не должно падать из-за чтения тоглов
        logger.warning("bot commands: feature check failed for %s", feature, exc_info=True)
        return True


def build_commands(entries: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [
        {"command": command, "description": description}
        for command, description in entries
        if _command_enabled(command)
    ]


def sync_bot_commands(db: Session, bot_token: str) -> dict[str, Any]:
    """Default list for everyone, then a per-chat admin list for linked admins."""
    result: dict[str, Any] = {"default": False, "admins": {}, "errors": []}
    ok, error = set_my_commands_sync(bot_token, build_commands(i18n.BOT_COMMANDS_USER))
    result["default"] = ok
    if not ok and error:
        result["errors"].append(error)

    admins = (
        db.query(User)
        .filter(User.role == UserRole.admin, User.telegram_id.isnot(None))
        .all()
    )
    for admin in admins:
        chat_id = (admin.telegram_id or "").strip()
        if not chat_id.lstrip("-").isdigit():
            continue
        ok_admin, err_admin = set_my_commands_sync(
            bot_token,
            build_commands(i18n.BOT_COMMANDS_ADMIN),
            scope={"type": "chat", "chat_id": int(chat_id)},
        )
        result["admins"][admin.username] = ok_admin
        if not ok_admin and err_admin:
            result["errors"].append(f"{admin.username}: {err_admin}")
    return result
