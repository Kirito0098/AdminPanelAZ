"""Lifecycle helpers for the Telegram application module."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import AppSetting
from app.services.telegram_api import delete_webhook_sync

logger = logging.getLogger(__name__)


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


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
