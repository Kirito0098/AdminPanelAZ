"""Shared 5-field cron matching (minute, hour, dom, month, dow)."""

from __future__ import annotations

from datetime import datetime, timezone


def cron_weekday_value(now: datetime) -> int:
    """Cron day-of-week: Sunday=0, Monday=1, ... Saturday=6."""
    return (now.weekday() + 1) % 7


def cron_field_matches(field: str, value: int) -> bool:
    field = (field or "").strip()
    if field == "*":
        return True
    if field.isdigit():
        return int(field) == value
    return False


def cron_matches_now(cron_expr: str, now: datetime | None = None) -> bool:
    """Match standard 5-field cron for the given UTC minute."""
    now = now or datetime.now(timezone.utc)
    parts = (cron_expr or "").strip().split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    checks = (
        (minute, now.minute),
        (hour, now.hour),
        (dom, now.day),
        (month, now.month),
        (dow, cron_weekday_value(now)),
    )
    return all(cron_field_matches(field, value) for field, value in checks)
