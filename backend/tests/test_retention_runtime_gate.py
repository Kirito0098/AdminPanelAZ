"""Retention worker runtime gate for RETENTION_ENABLED settings flip."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.retention_worker as worker


def test_retention_loop_skips_purge_when_disabled(monkeypatch):
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("purge must not run while retention is disabled")

    monkeypatch.setattr(worker, "_purge_once", boom)

    class _Settings:
        retention_enabled = False
        retention_interval_hours = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_retention_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_retention_loop_purges_when_enabled(monkeypatch):
    called = {"n": 0}

    def mark():
        called["n"] += 1

    monkeypatch.setattr(worker, "_purge_once", mark)

    class _Settings:
        retention_enabled = True
        retention_interval_hours = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 1:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_retention_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 1


def test_should_start_retention_always_true(monkeypatch):
    from app.services import worker_lifecycle as lifecycle

    class _Off:
        retention_enabled = False

    monkeypatch.setattr(lifecycle, "get_settings", lambda: _Off())
    assert lifecycle.should_start_retention() is True
