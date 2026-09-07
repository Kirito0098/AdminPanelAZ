"""Scheduled daily/weekly NOC summary reports to admin Telegram (per-user)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import AppSetting
from app.services.noc_report import send_noc_report, send_weekly_image_report
from app.services.noc_schedule import (
    local_now_for_user,
    should_run_daily,
    should_run_weekly,
)

logger = logging.getLogger(__name__)


def _is_telegram_enabled() -> bool:
    """Runtime gate — telegram module can flip without restart."""
    from app.services.feature_guards import get_feature_service

    return get_feature_service().is_enabled("telegram")


def _last_run_key(period: str, user_id: int) -> str:
    return f"noc_report_{period}_last_run:{user_id}"


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


def _already_ran_local_minute(db: Session, key: str, local_now: datetime) -> bool:
    last_raw = _get_setting(db, key, "")
    if not last_raw:
        return False
    try:
        last = datetime.fromisoformat(last_raw.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        last_local = last.astimezone(local_now.tzinfo)
        return (
            last_local.year == local_now.year
            and last_local.month == local_now.month
            and last_local.day == local_now.day
            and last_local.hour == local_now.hour
            and last_local.minute == local_now.minute
        )
    except ValueError:
        return False


def _actually_delivered(result: dict | None) -> bool:
    """True only when at least one Telegram delivery succeeded."""
    if not result:
        return False
    try:
        return int(result.get("sent") or 0) > 0
    except (TypeError, ValueError):
        return False


def process_user_noc_tick(
    db: Session,
    user: Any,
    *,
    now: datetime,
    settings: Any,
) -> list[dict]:
    results: list[dict] = []
    local = local_now_for_user(user, now)

    if should_run_daily(user, now_utc=now, env_daily_cron=settings.noc_report_daily_cron):
        key = _last_run_key("daily", user.id)
        if not _already_ran_local_minute(db, key, local):
            result = send_noc_report(db, period="daily", recipients=[user])
            # Only stamp dedup on real delivery — skipped/zero-sent remain retryable.
            if _actually_delivered(result):
                _set_setting(db, key, now.isoformat())
            results.append({"user_id": user.id, "period": "daily", **result})

    if should_run_weekly(user, now_utc=now, env_weekly_cron=settings.noc_report_weekly_cron):
        key = _last_run_key("weekly", user.id)
        if not _already_ran_local_minute(db, key, local):
            result = send_noc_report(db, period="weekly", recipients=[user])
            if settings.noc_report_weekly_image_enabled:
                img = send_weekly_image_report(db, recipients=[user])
                result["image"] = img
            # Stamp if text OR weekly image was actually sent.
            if _actually_delivered(result) or _actually_delivered(result.get("image")):
                _set_setting(db, key, now.isoformat())
            results.append({"user_id": user.id, "period": "weekly", **result})

    return results


def run_noc_report_scheduler_tick(now: datetime | None = None) -> list[dict]:
    settings = get_settings()
    if not settings.noc_report_enabled:
        return [{"status": "disabled"}]

    now = now or datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        from app.services.noc_report import _notify_recipients

        results: list[dict] = []
        for user in _notify_recipients(db):
            try:
                results.extend(process_user_noc_tick(db, user, now=now, settings=settings))
            except Exception as exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                user_id = getattr(user, "id", None)
                logger.exception(
                    "NOC report scheduler tick failed for user %s: %s",
                    user_id,
                    exc,
                )
                results.append({"status": "error", "user_id": user_id, "error": str(exc)})
        return results
    except Exception as exc:
        logger.exception("NOC report scheduler tick failed: %s", exc)
        return [{"status": "error", "error": str(exc)}]
    finally:
        db.close()


async def run_noc_report_scheduler_loop() -> None:
    """NOC report loop — re-checks noc_report + telegram each tick."""
    while True:
        try:
            settings = get_settings()
            interval = max(30, int(settings.noc_report_check_interval_seconds or 60))
            await asyncio.sleep(interval)
            settings = get_settings()
            if not settings.noc_report_enabled:
                logger.debug("noc_report_scheduler skipped — NOC_REPORT_ENABLED disabled")
                continue
            if not _is_telegram_enabled():
                logger.debug("noc_report_scheduler skipped — telegram module disabled")
                continue
            results = await asyncio.to_thread(run_noc_report_scheduler_tick)
            for result in results:
                if result.get("status") == "sent":
                    logger.debug("NOC report scheduler: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("NOC report scheduler error: %s", exc)
