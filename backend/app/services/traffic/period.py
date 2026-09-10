"""Parse and validate traffic overview/chart period windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from app.services.notify_time import _normalize_timezone_name

_PRESET_DAYS: dict[str, int] = {"1d": 1, "7d": 7, "30d": 30}
_PRESET_LABELS: dict[str, str] = {"1d": "1 дн.", "7d": "7 дн.", "30d": "30 дн."}


class TrafficPeriodError(Exception):
    def __init__(self, message: str, retention_days: int) -> None:
        super().__init__(message)
        self.retention_days = retention_days


@dataclass(frozen=True)
class TrafficPeriodWindow:
    mode: Literal["preset", "custom"]
    period: str | None
    from_date: date | None
    to_date: date | None
    since_utc: datetime
    until_utc: datetime
    retention_days: int
    label: str


def _retention_error(retention_days: int) -> TrafficPeriodError:
    message = (
        f"Данные трафика хранятся только {retention_days} дн. "
        "(Настройки → Обслуживание)."
    )
    return TrafficPeriodError(message, retention_days)


def _resolve_tz(tz_name: str) -> ZoneInfo:
    normalized = _normalize_timezone_name(tz_name) or "UTC"
    return ZoneInfo(normalized)


def _to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _local_today(now: datetime, tz: ZoneInfo) -> date:
    return _to_naive_utc(now).replace(tzinfo=timezone.utc).astimezone(tz).date()


def _local_day_start_utc_naive(d: date, tz: ZoneInfo) -> datetime:
    local_start = datetime(d.year, d.month, d.day, tzinfo=tz)
    return local_start.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_iso_date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _custom_label(from_d: date, to_d: date) -> str:
    if from_d == to_d:
        return from_d.strftime("%d.%m.%Y")
    return f"{from_d.strftime('%d.%m.%Y')} — {to_d.strftime('%d.%m.%Y')}"


def resolve_traffic_period(
    *,
    period: str | None,
    from_s: str | None,
    to_s: str | None,
    retention_days: int,
    tz_name: str,
    now: datetime | None = None,
) -> TrafficPeriodWindow:
    if retention_days < 1:
        raise _retention_error(retention_days)

    tz = _resolve_tz(tz_name)
    instant = now if now is not None else datetime.now(timezone.utc)
    until_naive = _to_naive_utc(instant)

    from_parsed = _parse_iso_date(from_s)
    to_parsed = _parse_iso_date(to_s)

    if from_parsed is not None or to_parsed is not None:
        if from_parsed is None or to_parsed is None:
            raise _retention_error(retention_days)

        today = _local_today(instant, tz)
        if from_parsed > to_parsed or from_parsed > today or to_parsed > today:
            raise _retention_error(retention_days)

        earliest = today - timedelta(days=retention_days)
        if from_parsed < earliest or to_parsed < earliest:
            raise _retention_error(retention_days)
        if (to_parsed - from_parsed).days > retention_days:
            raise _retention_error(retention_days)

        since_utc = _local_day_start_utc_naive(from_parsed, tz)
        until_utc = _local_day_start_utc_naive(to_parsed + timedelta(days=1), tz)
        return TrafficPeriodWindow(
            mode="custom",
            period=None,
            from_date=from_parsed,
            to_date=to_parsed,
            since_utc=since_utc,
            until_utc=until_utc,
            retention_days=retention_days,
            label=_custom_label(from_parsed, to_parsed),
        )

    preset = (period or "30d").strip().lower()
    if preset not in _PRESET_DAYS:
        preset = "30d"
    days = _PRESET_DAYS[preset]
    since_utc = until_naive - timedelta(days=days)
    return TrafficPeriodWindow(
        mode="preset",
        period=preset,
        from_date=None,
        to_date=None,
        since_utc=since_utc,
        until_utc=until_naive,
        retention_days=retention_days,
        label=_PRESET_LABELS.get(preset, preset),
    )


def chart_bucket_for_window(
    window: TrafficPeriodWindow,
    *,
    range_key: str | None = None,
) -> str:
    if window.mode == "preset":
        key = (range_key or window.period or "7d").strip().lower()
        if key == "24h":
            key = "1d"
        if key == "1h":
            return "minute5"
        if key == "1d":
            return "hour"
        if key in ("7d", "30d"):
            return "day"
        if key == "all":
            return "month"
        return "day"

    assert window.from_date is not None and window.to_date is not None
    span_days = (window.to_date - window.from_date).days + 1
    if span_days <= 2:
        return "hour"
    if span_days <= 90:
        return "day"
    return "month"
