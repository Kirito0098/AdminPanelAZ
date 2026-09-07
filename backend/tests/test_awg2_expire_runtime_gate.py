"""AWG2 expire worker runtime gate for the awg2 feature toggle."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.services.awg2_expire_worker as worker


def test_expire_loop_skips_reconcile_when_module_disabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_awg2_module_enabled", lambda: False)
    monkeypatch.setattr(worker, "AWG2_EXPIRE_INTERVAL_SECONDS", 0)
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("reconcile must not run while awg2 is disabled")

    monkeypatch.setattr(worker, "run_awg2_expire_once", boom)

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_awg2_expire_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_is_awg2_module_enabled_delegates(monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_toggles.is_awg2_enabled",
        lambda db=None: False,
    )
    assert worker._is_awg2_module_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_toggles.is_awg2_enabled",
        lambda db=None: True,
    )
    assert worker._is_awg2_module_enabled() is True


def test_should_start_awg2_expire_always_true(monkeypatch):
    from app.services import worker_lifecycle as lifecycle

    monkeypatch.setattr(
        lifecycle,
        "get_feature_service",
        lambda: type("F", (), {"is_enabled": staticmethod(lambda _k: False)})(),
    )
    assert lifecycle.should_start_awg2_expire() is True
