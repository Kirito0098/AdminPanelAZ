from datetime import datetime, timezone

import pytest

import app.services.warper as warper_mod
from app.services.warper import _chart_points_from_hourly, _filter_traffic_hourly, enrich_warper_traffic_payload


def test_today_filter_uses_local_day(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = cls(2026, 9, 7, 1, 30, tzinfo=timezone.utc)
            return base if tz is None else base.astimezone(tz)

    monkeypatch.setattr(warper_mod, "datetime", FixedDateTime)

    hourly = {
        "2026-09-06T22": {"rx": 1, "tx": 0},  # 01:00 MSK Sep 7
        "2026-09-06T20": {"rx": 2, "tx": 0},  # 23:00 MSK Sep 6
    }

    points = _filter_traffic_hourly(hourly, "today", tz_name="Europe/Moscow")
    assert [point["ts"] for point in points] == ["2026-09-06T22"]


def test_week_points_group_by_local_day(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = cls(2026, 9, 7, 1, 30, tzinfo=timezone.utc)
            return base if tz is None else base.astimezone(tz)

    monkeypatch.setattr(warper_mod, "datetime", FixedDateTime)

    hourly_points = [
        {"ts": "2026-09-06T20", "rx": 2, "tx": 1},  # 23:00 MSK Sep 6
        {"ts": "2026-09-06T22", "rx": 1, "tx": 3},  # 01:00 MSK Sep 7
        {"ts": "2026-09-07T01", "rx": 4, "tx": 0},  # 04:00 MSK Sep 7
    ]

    points = _chart_points_from_hourly(hourly_points, "week", tz_name="Europe/Moscow")

    assert len(points) == 2
    assert points[0]["ts"].startswith("2026-09-05T21:00:00")
    assert points[0]["rx"] == 2
    assert points[0]["tx"] == 1
    assert points[1]["ts"].startswith("2026-09-06T21:00:00")
    assert points[1]["rx"] == 5
    assert points[1]["tx"] == 3


@pytest.mark.parametrize(
    ("period", "included_ts", "excluded_ts"),
    [
        ("week", "2026-08-30T21", "2026-08-30T20"),
        ("month", "2026-08-07T21", "2026-08-07T20"),
    ],
)
def test_week_and_month_start_at_local_day_boundary(monkeypatch, period, included_ts, excluded_ts):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = cls(2026, 9, 7, 1, 30, tzinfo=timezone.utc)
            return base if tz is None else base.astimezone(tz)

    monkeypatch.setattr(warper_mod, "datetime", FixedDateTime)

    hourly = {
        excluded_ts: {"rx": 1, "tx": 0},
        included_ts: {"rx": 2, "tx": 0},
    }

    points = _filter_traffic_hourly(hourly, period, tz_name="Europe/Moscow")

    assert [point["ts"] for point in points] == [included_ts]


def test_enrich_rebuilds_from_full_hourly_map(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = cls(2026, 9, 7, 1, 30, tzinfo=timezone.utc)
            return base if tz is None else base.astimezone(tz)

    monkeypatch.setattr(warper_mod, "datetime", FixedDateTime)
    monkeypatch.setattr(
        warper_mod,
        "_read_traffic_hourly_map",
        lambda: {
            "2026-09-05T20": {"rx": 99, "tx": 99},
            "2026-09-05T21": {"rx": 88, "tx": 88},
        },
    )

    payload = {
        "hourly_points": [
            {"ts": "2026-09-06T20", "rx": 9, "tx": 1},  # local Sep 6, should stay out of "today"
            {"ts": "2026-09-06T22", "rx": 2, "tx": 1},  # local Sep 7, should be recovered
            {"ts": "2026-09-07T01", "rx": 4, "tx": 3},
        ]
    }

    enriched = enrich_warper_traffic_payload(payload, "today", tz_name="Europe/Moscow")

    assert [point["ts"] for point in enriched["hourly_points"]] == [
        "2026-09-06T20",
        "2026-09-06T22",
        "2026-09-07T01",
    ]
    assert [point["ts"] for point in enriched["chart"]] == [
        "2026-09-06T22",
        "2026-09-07T01",
    ]
    assert all(point["rx"] != 99 for point in enriched["chart"])
    assert all(point["tx"] != 99 for point in enriched["chart"])


def test_enrich_falls_back_to_local_hourly_map_when_payload_missing_history(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = cls(2026, 9, 7, 1, 30, tzinfo=timezone.utc)
            return base if tz is None else base.astimezone(tz)

    monkeypatch.setattr(warper_mod, "datetime", FixedDateTime)
    monkeypatch.setattr(
        warper_mod,
        "_read_traffic_hourly_map",
        lambda: {
            "2026-09-06T20": {"rx": 9, "tx": 1},  # local Sep 6, should stay out of "today"
            "2026-09-06T22": {"rx": 2, "tx": 1},  # local Sep 7, should be recovered
            "2026-09-07T01": {"rx": 4, "tx": 3},  # local Sep 7, should be recovered
        },
    )

    enriched = enrich_warper_traffic_payload({}, "today", tz_name="Europe/Moscow")

    assert [point["ts"] for point in enriched["chart"]] == [
        "2026-09-06T22",
        "2026-09-07T01",
    ]
