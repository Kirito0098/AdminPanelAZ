from datetime import datetime, timezone

from app.services.chart_timezone import (
    local_bucket_start_as_utc_iso,
    naive_utc_to_local,
    resolve_chart_timezone,
)


def test_resolve_prefers_explicit_then_falls_back_utc():
    assert resolve_chart_timezone(explicit="Europe/Moscow") == "Europe/Moscow"
    assert resolve_chart_timezone(explicit="Not/AZone") == "UTC"
    assert resolve_chart_timezone() == "UTC"


def test_naive_utc_to_moscow():
    local = naive_utc_to_local(datetime(2026, 9, 7, 8, 56, 0), "Europe/Moscow")
    assert local.hour == 11
    assert local.tzinfo is not None


def test_hour_bucket_start_iso_moscow():
    local = naive_utc_to_local(datetime(2026, 9, 7, 8, 56, 0), "Europe/Moscow")
    iso = local_bucket_start_as_utc_iso(local, "hour")
    # Local 11:00 MSK == 08:00 UTC
    assert iso.startswith("2026-09-07T08:00:00")
