"""Nightly panel restart when no active web sessions (ported from AdminAntizapret)."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import AppSetting
from app.services.active_web_session import active_web_session_service

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
    db.commit()


def _cron_field_matches(field: str, value: int) -> bool:
    field = (field or "").strip()
    if field == "*":
        return True
    if field.isdigit():
        return int(field) == value
    return False


def cron_matches_now(cron_expr: str, now: datetime | None = None) -> bool:
    """Match standard 5-field cron for exact minute/hour and wildcard day/month/dow."""
    now = now or datetime.now(timezone.utc)
    parts = (cron_expr or "").strip().split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    if not _cron_field_matches(minute, now.minute):
        return False
    if not _cron_field_matches(hour, now.hour):
        return False
    for field in (dom, month, dow):
        if field != "*":
            return False
    return True


def _already_ran_this_minute(db: Session, now: datetime) -> bool:
    last_raw = _get_setting(db, "nightly_idle_restart_last_run", "")
    if not last_raw:
        return False
    try:
        last = datetime.fromisoformat(last_raw.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tinfo=timezone.utc)
        return (
            last.year == now.year
            and last.month == now.month
            and last.day == now.day
            and last.hour == now.hour
            and last.minute == now.minute
        )
    except ValueError:
        return False


def run_nightly_idle_restart_once() -> dict:
    settings = get_settings()
    if not settings.nightly_idle_restart_enabled:
        return {"status": "disabled"}

    now = datetime.now(timezone.utc)
    if not cron_matches_now(settings.nightly_idle_restart_cron, now):
        return {"status": "skipped", "reason": "cron_mismatch"}

    db = SessionLocal()
    try:
        if _already_ran_this_minute(db, now):
            return {"status": "skipped", "reason": "already_ran"}

        active_web_session_service.cleanup_stale_for_nightly(db)
        active_count = active_web_session_service.count_active_sessions(db)
        if active_count > 0:
            logger.info("Nightly idle restart skipped: active sessions=%s", active_count)
            _set_setting(db, "nightly_idle_restart_last_run", now.isoformat())
            return {"status": "skipped", "reason": "active_sessions", "active_count": active_count}

        service_name = settings.admin_panel_az_service_name.strip() or "admin-panel-az.service"
        subprocess.run(
            ["systemctl", "restart", service_name],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        _set_setting(db, "nightly_idle_restart_last_run", now.isoformat())
        logger.info("Nightly idle restart: service restarted (%s)", service_name)
        return {"status": "restarted", "service": service_name}
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        logger.error("Nightly idle restart failed: %s", err)
        return {"status": "error", "error": err}
    except Exception as exc:
        logger.exception("Nightly idle restart failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()


async def run_nightly_idle_restart_loop() -> None:
    settings = get_settings()
    if not settings.nightly_idle_restart_enabled:
        return

    while True:
        try:
            await asyncio.sleep(60)
            result = await asyncio.to_thread(run_nightly_idle_restart_once)
            if result.get("status") == "restarted":
                logger.info("Nightly idle restart worker: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Nightly idle restart worker error: %s", exc)
