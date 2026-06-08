"""Notification timestamp formatting tests (ported from AdminAntizapret)."""

from app.services.notify_time import _normalize_timezone_name, format_notify_when


def test_normalize_timezone_valid():
    assert _normalize_timezone_name("Europe/Moscow") == "Europe/Moscow"


def test_normalize_timezone_invalid():
    assert _normalize_timezone_name("Not/A/Zone") is None


def test_format_notify_when_utc_fallback():
    text = format_notify_when(None)
    assert text.endswith(" UTC")
    parts = text.split()
    assert len(parts) == 3
    assert parts[0].count("-") == 2


def test_format_notify_when_client_zone():
    text = format_notify_when("Europe/Moscow")
    assert " UTC" not in text
    assert len(text.split()) >= 3
