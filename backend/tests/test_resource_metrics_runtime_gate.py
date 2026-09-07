"""Resource metrics worker runtime gate for resource_monitor toggle."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.resource_metrics_worker as worker


def test_resource_metrics_loop_skips_collect_when_monitor_disabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_resource_monitor_enabled", lambda: False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("collect must not run while resource_monitor is disabled")

    monkeypatch.setattr(worker, "_collect_all_nodes", boom)

    class _Settings:
        resource_metrics_enabled = True
        resource_metrics_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_resource_metrics_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_is_resource_monitor_enabled_delegates(monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )
    assert worker._is_resource_monitor_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(True),
    )
    assert worker._is_resource_monitor_enabled() is True


class SimpleEnabled:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self, key: str) -> bool:
        assert key == "resource_monitor"
        return self._enabled
