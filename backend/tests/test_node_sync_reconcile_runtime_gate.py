"""Node sync reconcile worker runtime gate for NODE_SYNC_RECONCILE_ENABLED."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.node_sync.reconcile_worker as worker


def test_node_sync_reconcile_loop_skips_when_disabled(monkeypatch):
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("reconcile must not run while disabled")

    monkeypatch.setattr(worker, "reconcile_sync_groups_safe", boom)

    class _Settings:
        node_sync_reconcile_enabled = False
        node_sync_reconcile_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_node_sync_reconcile_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_node_sync_reconcile_loop_runs_when_enabled(monkeypatch):
    called = {"n": 0}

    def mark():
        called["n"] += 1

    monkeypatch.setattr(worker, "reconcile_sync_groups_safe", mark)

    class _Settings:
        node_sync_reconcile_enabled = True
        node_sync_reconcile_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 1:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_node_sync_reconcile_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 1


def test_should_start_node_sync_reconcile_always_true(monkeypatch):
    from app.services import worker_lifecycle as lifecycle

    class _Off:
        node_sync_reconcile_enabled = False

    monkeypatch.setattr(lifecycle, "get_settings", lambda: _Off())
    assert lifecycle.should_start_node_sync_reconcile() is True
