"""Lifecycle helpers for the Telegram application module."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.services.app_setting_store import _get_setting, _set_setting
from app.services.telegram_api import delete_webhook_sync

logger = logging.getLogger(__name__)


def shutdown_telegram_integration(db: Session) -> dict[str, bool]:
    """Stop runtime Telegram activity while keeping stored bot credentials."""
    token = _get_setting(db, "telegram_bot_token").strip()
    webhook_deleted = False
    if token:
        try:
            delete_webhook_sync(token)
            webhook_deleted = True
        except Exception as exc:
            logger.warning("Failed to delete Telegram webhook on module shutdown: %s", exc)

    _set_setting(db, "telegram_bot_interactive_enabled", "false")
    _set_setting(db, "telegram_notify_enabled", "false")
    _set_setting(db, "backup_telegram_enabled", "false")
    _set_setting(db, "telegram_webhook_set_at", "")

    return {"webhook_deleted": webhook_deleted}
