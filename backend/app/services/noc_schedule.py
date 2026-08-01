"""Per-admin NOC report schedule matching (local HH:MM + optional env cron fallback)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.services.cron_schedule import cron_matches_now, cron_weekday_value
from app.services.notify_time import effective_user_timezone


def parse_hhmm(raw: str | None) -> tuple[int, int] | None:
    text = str(raw or "").strip()
    if not text or ":" not in text:
        return None
    left, _, right = text.partition(":")
    if not left.isdigit() or not right.isdigit():
        return None
    hour, minute = int(left), int(right)
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def parse_cron_dow(raw: str | None) -> int | None:
    text = str(raw or "").strip()
    if not text.isdigit():
        return None
    value = int(text)
    if value < 0 or value > 6:
        return None
    return value


def local_now_for_user(user: Any, now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    tz_name = effective_user_timezone(user) or "UTC"
    return now_utc.astimezone(ZoneInfo(tz_name))


def should_run_daily(user: Any, *, now_utc: datetime, env_daily_cron: str) -> bool:
    parsed = parse_hhmm(getattr(user, "noc_daily_time", None))
    if parsed is not None:
        local = local_now_for_user(user, now_utc)
        hour, minute = parsed
        return local.hour == hour and local.minute == minute
    return cron_matches_now(env_daily_cron, now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc))


def should_run_weekly(user: Any, *, now_utc: datetime, env_weekly_cron: str) -> bool:
    dow = parse_cron_dow(getattr(user, "noc_weekly_dow", None))
    parsed = parse_hhmm(getattr(user, "noc_weekly_time", None))
    if dow is not None and parsed is not None:
        local = local_now_for_user(user, now_utc)
        hour, minute = parsed
        return cron_weekday_value(local) == dow and local.hour == hour and local.minute == minute
    return cron_matches_now(env_weekly_cron, now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc))
