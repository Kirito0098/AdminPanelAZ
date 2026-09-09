from datetime import datetime, timezone

import app.services.warper as warper_mod
from app.services.warper import _chart_points_from_hourly, _filter_traffic_hourly


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
