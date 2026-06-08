"""Backup scheduler helpers (ported from AdminAntizapret maintenance_scheduler backup tests)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.models import AppSetting
from app.services.backup_scheduler import _should_run


def _session_with_setting(key: str, value: str):
    db = MagicMock()
    row = AppSetting(key=key, value=value) if value else None
    db.query.return_value.filter.return_value.first.return_value = row
    return db


def test_should_run_when_never_ran():
    db = _session_with_setting("backup_auto_last_run", "")
    assert _should_run("backup_auto_last_run", 7, db) is True


def test_should_run_when_interval_elapsed():
    last = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    db = _session_with_setting("backup_auto_last_run", last)
    assert _should_run("backup_auto_last_run", 7, db) is True


def test_should_not_run_when_interval_not_elapsed():
    last = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    db = _session_with_setting("backup_auto_last_run", last)
    assert _should_run("backup_auto_last_run", 7, db) is False


def test_should_run_on_invalid_last_run_timestamp():
    db = _session_with_setting("backup_auto_last_run", "not-a-date")
    assert _should_run("backup_auto_last_run", 7, db) is True
