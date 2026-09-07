"""User reminder worker runtime gate for SELF_SERVICE_REMINDER_ENABLED."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import app.services.user_reminder_worker as worker


def test_user_reminder_loop_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_user_reminder_enabled", lambda: False)

    class _Settings:
        self_service_reminder_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    session_factory = MagicMock()
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_user_reminder_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    session_factory.assert_not_called()
    assert sleeps >= 2


def test_user_reminder_loop_processes_when_enabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_user_reminder_enabled", lambda: True)
    called = {"n": 0}

    def mark(_db):
        called["n"] += 1
        return 0

    monkeypatch.setattr(worker, "process_user_reminders", mark)

    class _Settings:
        self_service_reminder_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    db = MagicMock()
    monkeypatch.setattr(worker, "SessionLocal", lambda: db)

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_user_reminder_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 1
    db.close.assert_called_once()


def test_is_user_reminder_enabled_delegates(monkeypatch):
    class _Off:
        self_service_reminder_enabled = False

    class _On:
        self_service_reminder_enabled = True

    monkeypatch.setattr(worker, "get_settings", lambda: _Off())
    assert worker._is_user_reminder_enabled() is False
    monkeypatch.setattr(worker, "get_settings", lambda: _On())
    assert worker._is_user_reminder_enabled() is True


def test_should_start_user_reminders_always_true(monkeypatch):
    from app.services import worker_lifecycle as lifecycle

    class _Off:
        self_service_reminder_enabled = False

    monkeypatch.setattr(lifecycle, "get_settings", lambda: _Off())
    assert lifecycle.should_start_user_reminders() is True
