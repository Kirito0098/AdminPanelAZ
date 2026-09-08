"""Traffic collector worker runtime gate for traffic_sync toggle."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.traffic.worker as worker


class SimpleEnabled:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self, key: str) -> bool:
        assert key == "traffic_sync"
        return self._enabled


def test_traffic_collector_loop_skips_collect_when_sync_disabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_traffic_sync_enabled", lambda: False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("collect must not run while traffic_sync is disabled")

    monkeypatch.setattr(worker, "_collect_all_nodes", boom)

    class _Settings:
        traffic_sync_enabled = True
        traffic_sync_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_traffic_collector_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_is_traffic_sync_enabled_delegates(monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )
    assert worker._is_traffic_sync_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(True),
    )
    assert worker._is_traffic_sync_enabled() is True


def test_traffic_collector_loop_runs_even_when_settings_disabled_at_start(monkeypatch):
    monkeypatch.setattr(worker, "_is_traffic_sync_enabled", lambda: False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("collect must not run while traffic_sync is disabled")

    monkeypatch.setattr(worker, "_collect_all_nodes", boom)

    class _Off:
        traffic_sync_enabled = False
        traffic_sync_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Off())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_traffic_collector_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_should_start_traffic_collector_always_true(monkeypatch):
    from app.services import worker_lifecycle as lifecycle

    class _Off:
        traffic_sync_enabled = False

    monkeypatch.setattr(lifecycle, "get_settings", lambda: _Off())
    assert lifecycle.should_start_traffic_collector() is True
