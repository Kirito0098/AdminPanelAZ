"""Node key rotation loop runtime gate for rotation-days setting."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import app.services.node_key_rotation as worker


class SimpleEnabled:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self, key: str) -> bool:
        assert key == "key_rotation"
        return self._enabled


def test_key_rotation_loop_skips_when_days_disabled(monkeypatch):
    class _Settings:
        node_api_key_rotation_check_hours = 0
        node_api_key_rotation_days = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    session_factory = MagicMock()
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_node_key_rotation_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    session_factory.assert_not_called()
    assert sleeps >= 2


def test_is_key_rotation_enabled_delegates(monkeypatch):
    class _Settings:
        node_api_key_rotation_days = 7

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )
    assert worker._is_key_rotation_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(True),
    )
    assert worker._is_key_rotation_enabled() is True


def test_key_rotation_loop_skips_when_feature_disabled(monkeypatch):
    class _Settings:
        node_api_key_rotation_check_hours = 0
        node_api_key_rotation_days = 7

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )

    session_factory = MagicMock()
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    monkeypatch.setattr(worker, "_nodes_due_for_rotation", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rotation query must not run while feature is disabled")))

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_node_key_rotation_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    session_factory.assert_not_called()
    assert sleeps >= 2


def test_should_start_key_rotation_always_true(monkeypatch):
    from app.services import worker_lifecycle as lifecycle

    class _Off:
        node_api_key_rotation_days = 0

    monkeypatch.setattr(lifecycle, "get_settings", lambda: _Off())
    assert lifecycle.should_start_key_rotation() is True
