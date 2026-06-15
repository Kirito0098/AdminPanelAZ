"""Tests for Telegram bot UI helpers."""

from app.services.telegram_bot_handlers.ui import format_bot_timestamp, role_label


def test_role_label_russian():
    assert role_label("admin") == "Администратор"
    assert role_label("viewer") == "Наблюдатель"


def test_format_bot_timestamp_iso():
    assert format_bot_timestamp("2026-06-15T12:30:00") == "15.06.2026 12:30 UTC"
