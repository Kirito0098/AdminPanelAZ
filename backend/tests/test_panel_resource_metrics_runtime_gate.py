"""Panel resource metrics worker runtime gate for resource_monitor toggle."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.panel_resource_metrics_worker as worker


class SimpleEnabled:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self, key: str) -> bool:
        assert key == "resource_monitor"
        return self._enabled


def test_panel_metrics_loop_skips_then_resumes_when_enabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_resource_monitor_enabled", lambda: True)
    called = {"n": 0}

    def collect():
        called["n"] += 1

    monkeypatch.setattr(worker, "_collect_sample", collect)

    class _Settings:
        panel_resource_metrics_enabled = False
        panel_resource_metrics_interval_seconds = 0
        retention_enabled = True

    settings = _Settings()
    monkeypatch.setattr(worker, "get_settings", lambda: settings)

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            settings.panel_resource_metrics_enabled = True
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_panel_resource_metrics_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 1
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


def test_should_start_panel_resource_metrics_always_true():
    from app.services import worker_lifecycle as lifecycle

    assert lifecycle.should_start_panel_resource_metrics() is True
