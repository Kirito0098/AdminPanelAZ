"""Scheduled daily/weekly NOC summary reports to admin Telegram."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import AppSetting
from app.services.cron_schedule import cron_matches_now
from app.services.noc_report import send_noc_report, send_weekly_image_report

logger = logging.getLogger(__name__)

_LAST_RUN_KEYS = {
    "daily": "noc_report_daily_last_run",
    "weekly": "noc_report_weekly_last_run",
}


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


def _already_ran_this_minute(db: Session, last_run_key: str, now: datetime) -> bool:
    last_raw = _get_setting(db, last_run_key, "")
    if not last_raw:
        return False
    try:
        last = datetime.fromisoformat(last_raw.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (
            last.year == now.year
            and last.month == now.month
            and last.day == now.day
            and last.hour == now.hour
            and last.minute == now.minute
        )
    except ValueError:
        return False


def run_noc_report_once(*, period: str, cron_expr: str, now: datetime | None = None) -> dict:
    settings = get_settings()
    if not settings.noc_report_enabled:
        return {"status": "disabled", "period": period}

    now = now or datetime.now(timezone.utc)
    if not cron_matches_now(cron_expr, now):
        return {"status": "skipped", "reason": "cron_mismatch", "period": period}

    last_run_key = _LAST_RUN_KEYS[period]
    db = SessionLocal()
    try:
        if _already_ran_this_minute(db, last_run_key, now):
            return {"status": "skipped", "reason": "already_ran", "period": period}

        result = send_noc_report(db, period=period)
        if period == "weekly" and settings.noc_report_weekly_image_enabled:
            image_result = send_weekly_image_report(db)
            result["image"] = image_result
            if image_result.get("status") == "sent":
                logger.info(
                    "NOC weekly image sent to %d/%d admin(s)",
                    image_result.get("sent", 0),
                    image_result.get("recipients", 0),
                )
        if result.get("status") == "sent":
            _set_setting(db, last_run_key, now.isoformat())
            logger.info(
                "NOC %s report sent to %d/%d admin(s)",
                period,
                result.get("sent", 0),
                result.get("recipients", 0),
            )
        elif result.get("status") == "skipped":
            _set_setting(db, last_run_key, now.isoformat())
        return result
    except Exception as exc:
        logger.exception("NOC %s report failed: %s", period, exc)
        return {"status": "error", "period": period, "error": str(exc)}
    finally:
        db.close()


def run_noc_report_scheduler_tick(now: datetime | None = None) -> list[dict]:
    settings = get_settings()
    results: list[dict] = []
    for period, cron_expr in (
        ("daily", settings.noc_report_daily_cron),
        ("weekly", settings.noc_report_weekly_cron),
    ):
        results.append(run_noc_report_once(period=period, cron_expr=cron_expr, now=now))
    return results


async def run_noc_report_scheduler_loop() -> None:
    settings = get_settings()
    if not settings.noc_report_enabled:
        return

    interval = max(30, int(settings.noc_report_check_interval_seconds or 60))
    while True:
        try:
            await asyncio.sleep(interval)
            results = await asyncio.to_thread(run_noc_report_scheduler_tick)
            for result in results:
                if result.get("status") == "sent":
                    logger.debug("NOC report scheduler: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("NOC report scheduler error: %s", exc)
