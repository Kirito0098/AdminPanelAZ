"""Access remaining time formatting (ported from AdminAntizapret)."""

from datetime import datetime, timedelta

from app.services.access_remaining import format_access_remaining, is_access_expired


def test_none_returns_none():
    assert format_access_remaining(None) is None


def test_ten_days_left():
    now = datetime(2026, 5, 19, 10, 0, 0)
    expires = now + timedelta(days=10, hours=2)
    assert format_access_remaining(expires, now=now) == "10 дн."


def test_less_than_24_hours_shows_hours_and_minutes():
    now = datetime(2026, 5, 19, 10, 0, 0)
    expires = now + timedelta(hours=5, minutes=30)
    assert format_access_remaining(expires, now=now) == "5 ч. 30 мин."


def test_23_hours_59_minutes():
    now = datetime(2026, 5, 19, 10, 0, 0)
    expires = now + timedelta(hours=23, minutes=59)
    assert format_access_remaining(expires, now=now) == "23 ч. 59 мин."


def test_one_hour_only():
    now = datetime(2026, 5, 19, 10, 0, 0)
    expires = now + timedelta(hours=1)
    assert format_access_remaining(expires, now=now) == "1 ч."


def test_minutes_only():
    now = datetime(2026, 5, 19, 10, 0, 0)
    expires = now + timedelta(minutes=45)
    assert format_access_remaining(expires, now=now) == "45 мин."


def test_expired_two_hours_ago():
    now = datetime(2026, 5, 19, 10, 0, 0)
    expires = now - timedelta(hours=2)
    assert format_access_remaining(expires, now=now) == "срок истёк"


def test_parses_string_expires_at():
    now = datetime(2026, 5, 19, 10, 0, 0)
    expires = "2026-05-19 15:30:00"
    assert format_access_remaining(expires, now=now) == "5 ч. 30 мин."


def test_parses_openvpn_utc_string():
    now = datetime(2026, 5, 19, 10, 0, 0)
    expires = "2026-05-19 15:00 UTC"
    assert format_access_remaining(expires, now=now) == "5 ч."


def test_is_access_expired_future_within_one_day():
    now = datetime(2026, 5, 19, 10, 0, 0)
    expires = now + timedelta(hours=23, minutes=59)
    assert is_access_expired(expires, now=now) is False


def test_is_access_expired_past():
    now = datetime(2026, 5, 19, 10, 0, 0)
    expires = now - timedelta(hours=2)
    assert is_access_expired(expires, now=now) is True
