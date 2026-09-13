"""Access expiry worker runtime gate for FEATURE_ACCESS_EXPIRY_ENABLED."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.access_expiry_worker as worker


class SimpleEnabled:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self, key: str) -> bool:
        assert key == "access_expiry"
        return self._enabled


def test_access_expiry_loop_skips_when_feature_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("run_once must not run while access_expiry is disabled")

    monkeypatch.setattr(worker, "_run_once", boom)

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_access_expiry_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_is_access_expiry_enabled_delegates(monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )
    assert worker._is_access_expiry_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(True),
    )
    assert worker._is_access_expiry_enabled() is True
