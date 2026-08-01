"""Telegram notify timestamps must respect profile / last-seen client timezone."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.notify_time import (
    effective_user_timezone,
    format_notify_when,
    remember_client_timezone,
    resolve_notify_timezone,
)


def test_format_notify_when_uses_explicit_zone():
    text = format_notify_when("Europe/Moscow")
    assert "UTC" not in text
    assert text[:10].count("-") == 2


def test_format_notify_when_defaults_to_utc_without_zone():
    assert format_notify_when(None).endswith("UTC")
    assert format_notify_when("").endswith("UTC")


def test_effective_user_timezone_prefers_profile_over_last_seen():
    user = SimpleNamespace(timezone="Asia/Yekaterinburg", last_client_timezone="Europe/Moscow")
    assert effective_user_timezone(user) == "Asia/Yekaterinburg"


def test_effective_user_timezone_falls_back_to_last_seen_when_browser_mode():
    user = SimpleNamespace(timezone="", last_client_timezone="Europe/Moscow")
    assert effective_user_timezone(user) == "Europe/Moscow"


def test_effective_user_timezone_none_when_empty():
    user = SimpleNamespace(timezone="", last_client_timezone="")
    assert effective_user_timezone(user) is None


def test_resolve_notify_timezone_prefers_explicit():
    user = SimpleNamespace(timezone="Europe/Moscow", last_client_timezone="UTC")
    assert resolve_notify_timezone("Asia/Tokyo", user=user) == "Asia/Tokyo"


def test_resolve_notify_timezone_uses_user_when_explicit_missing():
    user = SimpleNamespace(timezone="", last_client_timezone="Europe/Moscow")
    assert resolve_notify_timezone(None, user=user) == "Europe/Moscow"


def test_resolve_notify_timezone_scans_users_list():
    empty = SimpleNamespace(timezone="", last_client_timezone="")
    moscow = SimpleNamespace(timezone="", last_client_timezone="Europe/Moscow")
    assert resolve_notify_timezone(None, users=[empty, moscow]) == "Europe/Moscow"


def test_remember_client_timezone_updates_last_seen_for_browser_mode():
    user = SimpleNamespace(timezone="", last_client_timezone="")
    db = MagicMock()
    assert remember_client_timezone(db, user, "Europe/Moscow") is True
    assert user.last_client_timezone == "Europe/Moscow"
    db.commit.assert_called_once()


def test_remember_client_timezone_can_skip_commit():
    user = SimpleNamespace(timezone="", last_client_timezone="")
    db = MagicMock()
    assert remember_client_timezone(db, user, "Europe/Moscow", commit=False) is True
    db.add.assert_called_once_with(user)
    db.commit.assert_not_called()


def test_remember_client_timezone_skips_invalid_and_unchanged():
    user = SimpleNamespace(timezone="", last_client_timezone="Europe/Moscow")
    db = MagicMock()
    assert remember_client_timezone(db, user, "Not/AZone") is False
    assert remember_client_timezone(db, user, "Europe/Moscow") is False
    db.commit.assert_not_called()
