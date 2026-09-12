"""Connection history worker runtime gate for resource_monitor toggle."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.connection_history_worker as worker


class SimpleEnabled:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self, key: str) -> bool:
        assert key in {"resource_monitor", "connection_history"}
        return self._enabled


def test_connection_history_loop_skips_collect_when_monitor_disabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_resource_monitor_enabled", lambda: False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("collect must not run while resource_monitor is disabled")

    monkeypatch.setattr(worker, "_collect_once", boom)

    class _Settings:
        resource_metrics_enabled = True
        resource_metrics_interval_seconds = 0
        retention_enabled = True

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_connection_history_loop()

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


def test_is_connection_history_enabled_delegates(monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )
    assert worker._is_connection_history_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(True),
    )
    assert worker._is_connection_history_enabled() is True


def test_collect_once_skips_purge_when_retention_enabled(monkeypatch):
    collected = {"n": 0}
    purged = {"n": 0}

    monkeypatch.setattr(
        worker,
        "collect_connection_samples",
        lambda _db: collected.__setitem__("n", collected["n"] + 1),
    )
    monkeypatch.setattr(
        worker,
        "purge_old_connection_samples",
        lambda _db: purged.__setitem__("n", purged["n"] + 1),
    )

    class _Db:
        def close(self):
            return None

    monkeypatch.setattr(worker, "SessionLocal", _Db)

    class _Settings:
        retention_enabled = True

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())
    worker._collect_once()
    assert collected["n"] == 1
    assert purged["n"] == 0


def test_connection_history_loop_runs_even_when_settings_disabled_at_start(monkeypatch):
    monkeypatch.setattr(worker, "_is_resource_monitor_enabled", lambda: False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("collect must not run while resource_monitor is disabled")

    monkeypatch.setattr(worker, "_collect_once", boom)

    class _Off:
        resource_metrics_enabled = False
        resource_metrics_interval_seconds = 0
        retention_enabled = True

    monkeypatch.setattr(worker, "get_settings", lambda: _Off())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_connection_history_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_should_start_connection_history_always_true(monkeypatch):
    from app.services import worker_lifecycle as lifecycle

    class _Off:
        resource_metrics_enabled = False

    monkeypatch.setattr(lifecycle, "get_settings", lambda: _Off())
    assert lifecycle.should_start_connection_history() is True


def test_connection_history_loop_skips_when_feature_disabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_resource_monitor_enabled", lambda: True)
    monkeypatch.setattr(worker, "_is_connection_history_enabled", lambda: False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("collect must not run while connection_history is disabled")

    monkeypatch.setattr(worker, "_collect_once", boom)

    class _Settings:
        resource_metrics_enabled = True
        resource_metrics_interval_seconds = 0
        retention_enabled = True

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_connection_history_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_collect_once_purges_when_retention_disabled(monkeypatch):
    purged = {"n": 0}
    monkeypatch.setattr(worker, "collect_connection_samples", lambda _db: None)
    monkeypatch.setattr(
        worker,
        "purge_old_connection_samples",
        lambda _db: purged.__setitem__("n", purged["n"] + 1),
    )

    class _Db:
        def close(self):
            return None

    monkeypatch.setattr(worker, "SessionLocal", _Db)

    class _Settings:
        retention_enabled = False

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())
    worker._collect_once()
    assert purged["n"] == 1
