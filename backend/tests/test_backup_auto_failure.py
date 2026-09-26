"""Auto-backup failure: the admin is told once per failure streak, the schedule keeps retrying."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.backup_scheduler as sched
from app.database import Base
from app.models import AppSetting
from app.services.admin_notify import admin_notify_service
from app.services.backup_manager import BackupManager


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        for key, value in {
            "backup_auto_enabled": "true",
            "backup_awg2_enabled": "false",
            "backup_az_enabled": "false",
            "backup_telegram_enabled": "false",
        }.items():
            db.add(AppSetting(key=key, value=value))
        db.commit()
    monkeypatch.setattr(sched, "SessionLocal", Session)
    monkeypatch.setattr(sched, "_is_backups_enabled", lambda: True)
    monkeypatch.setattr(sched, "collect_backup_config_contents", lambda _db: None)

    notices: list[dict] = []
    monkeypatch.setattr(
        admin_notify_service,
        "send_settings_change",
        lambda _db, **kwargs: notices.append(kwargs),
    )

    db_path = tmp_path / "adminpanel.db"
    sqlite3.connect(db_path).close()
    env_path = tmp_path / ".env"
    env_path.write_text("X=1\n", encoding="utf-8")
    paths = {
        "app_root": tmp_path,
        "backup_root": tmp_path / "backups",
        "db_path": db_path,
        "env_path": env_path,
        "cidr_db_path": None,
    }

    def setting(key: str) -> str | None:
        with Session() as db:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            return row.value if row else None

    return paths, notices, setting


def _fail(monkeypatch):
    def disk_full(self, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(BackupManager, "create_backup", disk_full)


def test_auto_backup_failure_notifies_once_per_streak(env, monkeypatch):
    paths, notices, setting = env
    real_create = BackupManager.create_backup
    _fail(monkeypatch)

    sched._run_auto_backup_once(**paths)
    sched._run_auto_backup_once(**paths)

    assert len(notices) == 1
    assert notices[0]["settings_key"] == "settings_backup_auto_failed"
    assert "No space left on device" in notices[0]["details"]
    assert setting("backup_auto_last_run") is None

    monkeypatch.setattr(BackupManager, "create_backup", real_create)
    sched._run_auto_backup_once(**paths)
    assert setting("backup_auto_last_run")
    assert not setting("backup_auto_last_error")

    with sched.SessionLocal() as db:
        db.query(AppSetting).filter(AppSetting.key == "backup_auto_last_run").delete()
        db.commit()
    _fail(monkeypatch)
    sched._run_auto_backup_once(**paths)
    assert len(notices) == 2


def test_auto_backup_failure_message_text():
    text = admin_notify_service._build_text(
        "settings_change",
        "system",
        "settings_backup_auto_failed",
        None,
        None,
        "OSError: <disk> full",
    )

    assert "Ошибка авто-бэкапа" in text
    assert "Авто-бэкап не создан, повтор через час: OSError: &lt;disk&gt; full" in text
