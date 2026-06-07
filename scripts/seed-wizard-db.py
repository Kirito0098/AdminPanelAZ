#!/usr/bin/env python3
"""Seed DB settings from install wizard (Telegram, auto-backup)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import AppSetting  # noqa: E402


def _set(db, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def main() -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if os.environ.get("WIZ_TELEGRAM_ENABLED") == "true":
            token = os.environ.get("WIZ_TELEGRAM_BOT_TOKEN", "").strip()
            chat = os.environ.get("WIZ_TELEGRAM_CHAT_ID", "").strip()
            if token:
                _set(db, "telegram_bot_token", token)
            if chat:
                _set(db, "telegram_chat_id", chat)
            _set(db, "telegram_notify_enabled", "true")

        if os.environ.get("WIZ_AUTO_BACKUP_ENABLED") == "true":
            _set(db, "backup_auto_enabled", "true")
            days = os.environ.get("WIZ_AUTO_BACKUP_DAYS", "7").strip() or "7"
            _set(db, "backup_auto_days", days)

        db.commit()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
