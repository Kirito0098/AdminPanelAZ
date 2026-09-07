"""NOC report scheduler runtime gate for NOC_REPORT_ENABLED / telegram."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.noc_report_scheduler as worker


class SimpleEnabled:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self, key: str) -> bool:
        assert key == "telegram"
        return self._enabled


def test_noc_report_loop_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_telegram_enabled", lambda: True)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("tick must not run while noc_report is disabled")

    monkeypatch.setattr(worker, "run_noc_report_scheduler_tick", boom)

    class _Settings:
        noc_report_enabled = False
        noc_report_check_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_noc_report_scheduler_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_noc_report_loop_skips_when_telegram_disabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_telegram_enabled", lambda: False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("tick must not run while telegram is disabled")

    monkeypatch.setattr(worker, "run_noc_report_scheduler_tick", boom)

    class _Settings:
        noc_report_enabled = True
        noc_report_check_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_noc_report_scheduler_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_noc_report_loop_ticks_when_enabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_telegram_enabled", lambda: True)
    called = {"n": 0}

    def mark():
        called["n"] += 1
        return []

    monkeypatch.setattr(worker, "run_noc_report_scheduler_tick", mark)

    class _Settings:
        noc_report_enabled = True
        noc_report_check_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_noc_report_scheduler_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 1


def test_is_telegram_enabled_delegates(monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )
    assert worker._is_telegram_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(True),
    )
    assert worker._is_telegram_enabled() is True


def test_should_start_noc_report_scheduler_always_true(monkeypatch):
    from app.services import worker_lifecycle as lifecycle

    class _Off:
        noc_report_enabled = False

    monkeypatch.setattr(lifecycle, "get_settings", lambda: _Off())
    monkeypatch.setattr(
        lifecycle,
        "get_feature_service",
        lambda: SimpleEnabled(False),
    )
    assert lifecycle.should_start_noc_report_scheduler() is True
