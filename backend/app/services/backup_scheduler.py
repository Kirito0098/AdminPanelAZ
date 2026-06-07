"""Scheduled auto-backup worker (ported from AdminAntizapret app_auto_backup.py)."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.database import SessionLocal
from app.models import AppSetting
from app.services.backup_manager import BackupManager
from app.services.telegram import send_tg_document

logger = logging.getLogger(__name__)


def _get_setting(db, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _should_run(last_run_key: str, interval_days: int, db) -> bool:
    last_raw = _get_setting(db, last_run_key, "")
    if not last_raw:
        return True
    try:
        last = datetime.fromisoformat(last_raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    return elapsed >= interval_days * 86400


async def run_backup_scheduler_loop(app_root: Path, backup_root: Path, db_path: Path, env_path: Path):
    """Background loop: check every hour if auto-backup should run."""
    while True:
        try:
            await asyncio.sleep(3600)
            db = SessionLocal()
            try:
                if _get_setting(db, "backup_auto_enabled", "false") != "true":
                    continue
                days = int(_get_setting(db, "backup_auto_days", "7") or "7")
                if not _should_run("backup_auto_last_run", days, db):
                    continue
                manager = BackupManager(
                    app_root=app_root,
                    backup_root=backup_root,
                    db_path=db_path,
                    env_path=env_path,
                )
                result = manager.create_backup(include_configs=True)
                row = db.query(AppSetting).filter(AppSetting.key == "backup_auto_last_run").first()
                now_str = datetime.now(timezone.utc).isoformat()
                if row:
                    row.value = now_str
                else:
                    db.add(AppSetting(key="backup_auto_last_run", value=now_str))
                retention = int(_get_setting(db, "backup_retention", "5") or "5")
                backups = manager.list_backups()
                for old in backups[retention:]:
                    try:
                        manager.delete_backup(old["file_name"])
                    except Exception:
                        pass
                if _get_setting(db, "backup_telegram_enabled", "false") == "true":
                    token = _get_setting(db, "telegram_bot_token")
                    chat = _get_setting(db, "telegram_chat_id")
                    if token and chat:
                        send_tg_document(token, chat, str(manager.get_backup_path(result["file_name"])),
                                         caption=f"Авто-бэкап: {result['file_name']}")
                db.commit()
                logger.info("Auto-backup created: %s", result["file_name"])
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Auto-backup scheduler error: %s", exc)
