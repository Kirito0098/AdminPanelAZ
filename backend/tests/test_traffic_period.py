from datetime import date, datetime, timezone

import pytest

from app.services.traffic.period import (
    TrafficPeriodError,
    chart_bucket_for_window,
    resolve_traffic_period,
)


def test_preset_30d_window():
    now = datetime(2026, 9, 10, 15, 0, 0, tzinfo=timezone.utc)
    w = resolve_traffic_period(
        period="30d", from_s=None, to_s=None, retention_days=90, tz_name="UTC", now=now
    )
    assert w.mode == "preset"
    assert w.period == "30d"
    assert (w.until_utc - w.since_utc).days == 30


def test_custom_inside_retention_ok():
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    w = resolve_traffic_period(
        period=None,
        from_s="2026-08-01",
        to_s="2026-08-31",
        retention_days=90,
        tz_name="UTC",
        now=now,
    )
    assert w.mode == "custom"
    assert w.from_date == date(2026, 8, 1)
    assert w.to_date == date(2026, 8, 31)


def test_custom_wider_than_retention_raises():
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(TrafficPeriodError) as ei:
        resolve_traffic_period(
            period=None,
            from_s="2026-01-01",
            to_s="2026-09-10",
            retention_days=90,
            tz_name="UTC",
            now=now,
        )
    assert ei.value.retention_days == 90
    assert "90" in str(ei.value)
    assert "хранятся" in str(ei.value)


def test_from_without_to_raises():
    with pytest.raises(TrafficPeriodError) as ei:
        resolve_traffic_period(
            period=None, from_s="2026-09-01", to_s=None, retention_days=90, tz_name="UTC"
        )
    assert "обе даты" in str(ei.value)


def test_both_garbage_date_strings_raises_not_preset():
    with pytest.raises(TrafficPeriodError) as ei:
        resolve_traffic_period(
            period="7d",
            from_s="not-a-date",
            to_s="also-garbage",
            retention_days=90,
            tz_name="UTC",
        )
    assert ei.value.retention_days == 90
    assert "формат" in str(ei.value).lower() or "ГГГГ" in str(ei.value)


def test_invalid_from_empty_to_raises():
    with pytest.raises(TrafficPeriodError) as ei:
        resolve_traffic_period(
            period=None,
            from_s="2026-13-40",
            to_s="",
            retention_days=90,
            tz_name="UTC",
        )
    assert "обе даты" in str(ei.value) or "формат" in str(ei.value).lower()


def test_valid_from_invalid_to_raises():
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(TrafficPeriodError) as ei:
        resolve_traffic_period(
            period=None,
            from_s="2026-09-01",
            to_s="bad",
            retention_days=90,
            tz_name="UTC",
            now=now,
        )
    assert "формат" in str(ei.value).lower() or "ГГГГ" in str(ei.value)


def test_from_after_to_distinct_message():
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(TrafficPeriodError) as ei:
        resolve_traffic_period(
            period=None,
            from_s="2026-09-08",
            to_s="2026-09-01",
            retention_days=90,
            tz_name="UTC",
            now=now,
        )
    assert "позже" in str(ei.value)


def test_future_date_distinct_message():
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(TrafficPeriodError) as ei:
        resolve_traffic_period(
            period=None,
            from_s="2026-09-11",
            to_s="2026-09-12",
            retention_days=90,
            tz_name="UTC",
            now=now,
        )
    assert "будущ" in str(ei.value)


def test_unknown_period_raises():
    with pytest.raises(TrafficPeriodError) as ei:
        resolve_traffic_period(
            period="99d", from_s=None, to_s=None, retention_days=90, tz_name="UTC"
        )
    assert "Неизвестный период" in str(ei.value)


def test_custom_overrides_period():
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    w = resolve_traffic_period(
        period="7d",
        from_s="2026-09-01",
        to_s="2026-09-05",
        retention_days=90,
        tz_name="UTC",
        now=now,
    )
    assert w.mode == "custom"


def test_chart_bucket_custom_lengths():
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    short = resolve_traffic_period(
        period=None, from_s="2026-09-09", to_s="2026-09-10", retention_days=90, tz_name="UTC", now=now
    )
    assert chart_bucket_for_window(short) == "hour"
    mid = resolve_traffic_period(
        period=None, from_s="2026-08-01", to_s="2026-08-31", retention_days=90, tz_name="UTC", now=now
    )
    assert chart_bucket_for_window(mid) == "day"
    # Full retention window: (to-from).days == 90 → 91 inclusive days — must stay daily.
    full = resolve_traffic_period(
        period=None, from_s="2026-06-12", to_s="2026-09-10", retention_days=90, tz_name="UTC", now=now
    )
    assert (full.to_date - full.from_date).days + 1 == 91
    assert chart_bucket_for_window(full) == "day"
