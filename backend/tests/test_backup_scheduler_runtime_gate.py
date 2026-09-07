"""Backup scheduler runtime gate for backups feature toggle."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import app.services.backup_scheduler as sched


class SimpleEnabled:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self, key: str) -> bool:
        assert key == "backups"
        return self._enabled


def test_backup_scheduler_skips_when_backups_disabled(monkeypatch):
    monkeypatch.setattr(sched, "_is_backups_enabled", lambda: False)
    opened = {"n": 0}

    class _BoomDb:
        def __init__(self):
            opened["n"] += 1
            raise AssertionError("db must not open while backups is disabled")

    monkeypatch.setattr(sched, "SessionLocal", _BoomDb)

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(sched.asyncio, "sleep", side_effect=fake_sleep):
            await sched.run_backup_scheduler_loop(
                app_root=Path("/tmp"),
                backup_root=Path("/tmp"),
                db_path=Path("/tmp/db"),
                env_path=Path("/tmp/.env"),
            )

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert opened["n"] == 0
    assert sleeps >= 2


def test_is_backups_enabled_delegates(monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )
    assert sched._is_backups_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(True),
    )
    assert sched._is_backups_enabled() is True
