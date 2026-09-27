"""Scheduler loops run their blocking work in a worker thread, not on the event loop."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import (
    backup_scheduler,
    cert_sync_worker,
    cloudflare_ips_scheduler,
    retention_worker,
    user_reminder_worker,
)
from app.services.cidr import cidr_scheduler


def _backup_loop():
    return backup_scheduler.run_backup_scheduler_loop(
        app_root=Path("/nonexistent"),
        backup_root=Path("/nonexistent/backups"),
        db_path=Path("/nonexistent/adminpanel.db"),
        env_path=Path("/nonexistent/.env"),
    )


def _cidr_setup(monkeypatch):
    monkeypatch.setattr(
        cidr_scheduler,
        "get_settings",
        lambda: SimpleNamespace(cidr_db_refresh_hour=3, cidr_db_refresh_minute=0, cidr_db_refresh_interval_days=1),
    )
    monkeypatch.setattr(cidr_scheduler, "_scheduler_may_run", lambda _settings: True)
    monkeypatch.setattr(cidr_scheduler, "_seconds_until_next_run", lambda _h, _m: 0)


def _cert_setup(monkeypatch):
    monkeypatch.setattr(cert_sync_worker, "get_settings", lambda: SimpleNamespace(cert_sync_interval_seconds=60))
    monkeypatch.setattr(cert_sync_worker, "_is_cert_sync_enabled", lambda: True)
    monkeypatch.setattr(cert_sync_worker, "_is_openvpn_module_enabled", lambda: True)


def _reminder_setup(monkeypatch):
    monkeypatch.setattr(
        user_reminder_worker, "get_settings", lambda: SimpleNamespace(self_service_reminder_interval_seconds=300)
    )
    monkeypatch.setattr(user_reminder_worker, "_is_user_reminder_enabled", lambda: True)


def _cleanup_loop():
    return backup_scheduler.run_runtime_backup_cleanup_loop(Path("/nonexistent/.env"))


def _cleanup_setup(monkeypatch):
    monkeypatch.setattr(
        backup_scheduler, "FeatureToggleService", lambda _path: SimpleNamespace(is_enabled=lambda _name: True)
    )


def _retention_setup(monkeypatch):
    monkeypatch.setattr(
        retention_worker, "get_settings", lambda: SimpleNamespace(retention_enabled=True, retention_interval_hours=0)
    )


LOOPS = [
    pytest.param(backup_scheduler, _backup_loop, "_run_auto_backup_once", None, id="backup"),
    pytest.param(
        cidr_scheduler, cidr_scheduler.run_cidr_db_scheduler_loop, "_run_scheduled_refresh", _cidr_setup, id="cidr"
    ),
    pytest.param(
        cloudflare_ips_scheduler,
        cloudflare_ips_scheduler.run_cloudflare_ips_scheduler_loop,
        "_refresh_cloudflare_ips_if_due",
        None,
        id="cloudflare_ips",
    ),
    pytest.param(
        backup_scheduler, _cleanup_loop, "_prune_runtime_backups", _cleanup_setup, id="runtime_backup_cleanup"
    ),
    pytest.param(retention_worker, retention_worker.run_retention_loop, "_purge_once", _retention_setup, id="retention"),
    pytest.param(cert_sync_worker, cert_sync_worker.run_cert_sync_loop, "_sync_cert_expiry_once", _cert_setup, id="cert_sync"),
    pytest.param(
        user_reminder_worker,
        user_reminder_worker.run_user_reminder_loop,
        "_process_user_reminders_once",
        _reminder_setup,
        id="user_reminders",
    ),
]


# Minutes of archiving, downloads or batch deletes must not hold the default executor
# that monitoring loops share.
LONG_LOOPS = {"backup", "runtime_backup_cleanup", "cidr", "retention"}


@pytest.mark.parametrize(("module", "loop_factory", "work_name", "setup"), LOOPS)
def test_loop_runs_work_off_the_event_loop_thread(monkeypatch, request, module, loop_factory, work_name, setup):
    if setup is not None:
        setup(monkeypatch)

    loop_thread: list[int] = []
    work_threads: list[int] = []
    work_thread_names: list[str] = []

    def work(*_args, **_kwargs):
        work_threads.append(threading.get_ident())
        work_thread_names.append(threading.current_thread().name)
        return []

    monkeypatch.setattr(module, work_name, work)
    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 2:
            raise asyncio.CancelledError()

    async def run():
        loop_thread.append(threading.get_ident())
        with patch.object(module.asyncio, "sleep", side_effect=fake_sleep):
            await loop_factory()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())

    assert work_threads, f"{work_name} was not called"
    assert all(ident != loop_thread[0] for ident in work_threads)
    is_long = request.node.callspec.id in LONG_LOOPS
    assert all(name.startswith("long-task") == is_long for name in work_thread_names), work_thread_names


def test_backup_work_is_skipped_when_module_disabled(monkeypatch):
    monkeypatch.setattr(backup_scheduler, "_is_backups_enabled", lambda: False)
    monkeypatch.setattr(
        backup_scheduler,
        "SessionLocal",
        lambda: pytest.fail("database opened while backups are disabled"),
    )
    backup_scheduler._run_auto_backup_once(
        app_root=Path("/nonexistent"),
        backup_root=Path("/nonexistent/backups"),
        db_path=Path("/nonexistent/adminpanel.db"),
        env_path=Path("/nonexistent/.env"),
        cidr_db_path=None,
    )

