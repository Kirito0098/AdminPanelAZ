"""Alert rules + nightly idle restart runtime gates."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.alert_rule_worker as alert_worker
import app.services.nightly_idle_restart_worker as nightly_worker


class _Toggle:
    def __init__(self, mapping: dict[str, bool]):
        self.mapping = mapping

    def is_enabled(self, key: str) -> bool:
        return self.mapping[key]


def test_alert_rules_loop_skips_when_runtime_disabled(monkeypatch):
    monkeypatch.setattr(alert_worker, "_is_alert_rules_runtime_enabled", lambda: False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("tick must not run while alert rules runtime gate is off")

    monkeypatch.setattr(alert_worker, "run_alert_rules_tick", boom)

    class _Settings:
        alert_rules_check_interval_seconds = 0

    monkeypatch.setattr(alert_worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(alert_worker.asyncio, "sleep", side_effect=fake_sleep):
            await alert_worker.run_alert_rules_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_alert_rules_runtime_requires_telegram(monkeypatch):
    class _On:
        alert_rules_enabled = True

    monkeypatch.setattr(alert_worker, "get_settings", lambda: _On())
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: _Toggle({"telegram": False}),
    )
    assert alert_worker._is_alert_rules_runtime_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: _Toggle({"telegram": True}),
    )
    assert alert_worker._is_alert_rules_runtime_enabled() is True


def test_nightly_loop_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(nightly_worker, "_is_nightly_idle_restart_enabled", lambda: False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("restart once must not run while disabled")

    monkeypatch.setattr(nightly_worker, "run_nightly_idle_restart_once", boom)

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(nightly_worker.asyncio, "sleep", side_effect=fake_sleep):
            await nightly_worker.run_nightly_idle_restart_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_should_start_alert_and_nightly_always_true():
    from app.services import worker_lifecycle as lifecycle

    assert lifecycle.should_start_alert_rules_worker() is True
    assert lifecycle.should_start_nightly_idle_restart() is True
