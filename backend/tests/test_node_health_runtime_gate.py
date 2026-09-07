"""Node health worker runtime gate for NODE_HEALTH_SYNC_ENABLED."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.node_health_worker as worker


def test_node_health_loop_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_node_health_sync_enabled", lambda: False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("poll must not run while node health sync is disabled")

    monkeypatch.setattr(worker, "_poll_all_nodes", boom)

    class _Settings:
        node_health_sync_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_node_health_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_node_health_loop_polls_when_enabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_node_health_sync_enabled", lambda: True)
    called = {"n": 0}

    def mark():
        called["n"] += 1

    monkeypatch.setattr(worker, "_poll_all_nodes", mark)

    class _Settings:
        node_health_sync_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 1:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_node_health_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 1


def test_should_start_node_health_always_true():
    from app.services import worker_lifecycle as lifecycle

    assert lifecycle.should_start_node_health() is True
