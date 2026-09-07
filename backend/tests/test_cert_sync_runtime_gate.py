"""Cert sync worker runtime gate for CERT_SYNC_ENABLED / openvpn."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import app.services.cert_sync_worker as worker


class SimpleEnabled:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self, key: str) -> bool:
        assert key == "openvpn"
        return self._enabled


def test_cert_sync_loop_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(worker, "INITIAL_DELAY_SECONDS", 0)
    monkeypatch.setattr(worker, "_is_cert_sync_enabled", lambda: False)
    monkeypatch.setattr(worker, "_is_openvpn_module_enabled", lambda: True)

    class _Settings:
        cert_sync_interval_seconds = 0

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
            await worker.run_cert_sync_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    session_factory.assert_not_called()
    assert sleeps >= 2


def test_cert_sync_loop_skips_when_openvpn_disabled(monkeypatch):
    monkeypatch.setattr(worker, "INITIAL_DELAY_SECONDS", 0)
    monkeypatch.setattr(worker, "_is_cert_sync_enabled", lambda: True)
    monkeypatch.setattr(worker, "_is_openvpn_module_enabled", lambda: False)

    class _Settings:
        cert_sync_interval_seconds = 0

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
            await worker.run_cert_sync_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    session_factory.assert_not_called()


def test_is_openvpn_module_enabled_delegates(monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )
    assert worker._is_openvpn_module_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(True),
    )
    assert worker._is_openvpn_module_enabled() is True


def test_should_start_cert_sync_always_true():
    from app.services import worker_lifecycle as lifecycle

    assert lifecycle.should_start_cert_sync() is True
