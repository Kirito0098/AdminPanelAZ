"""D1: group/channel Telegram backups require a password; archives are encrypted when set."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AppSetting
from app.routers import backups as backups_router
from app.services import backup_scheduler, backup_telegram_privacy as privacy
from app.services.admin_notify import admin_notify_service


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


class FakeManager:
    def __init__(self, panel_archive: Path):
        self._panel_archive = panel_archive

    def create_backup(self, **_kwargs):
        return {"file_name": self._panel_archive.name}

    def get_backup_path(self, _name):
        return self._panel_archive


def test_group_chat_ids_are_detected():
    assert privacy.is_group_or_channel_chat_id("-1001234567890")
    assert privacy.is_group_or_channel_chat_id("-42")
    assert not privacy.is_group_or_channel_chat_id("123456789")
    assert not privacy.is_group_or_channel_chat_id("42")


def test_filter_skips_groups_without_password():
    allowed, skipped = privacy.filter_backup_telegram_recipients(
        ["111", "-100222", "333"],
        password_set=False,
    )
    assert allowed == ["111", "333"]
    assert skipped == ["-100222"]


def test_filter_keeps_groups_when_password_set():
    allowed, skipped = privacy.filter_backup_telegram_recipients(
        ["111", "-100222"],
        password_set=True,
    )
    assert allowed == ["111", "-100222"]
    assert skipped == []


def test_encrypt_decrypt_roundtrip(tmp_path: Path):
    src = tmp_path / "panel.tar.gz"
    src.write_bytes(b"backup-bytes-secret")
    enc = privacy.encrypt_backup_bytes(src.read_bytes(), "s3cret")
    assert privacy.is_encrypted_backup_bytes(enc)
    assert enc != src.read_bytes()
    assert privacy.decrypt_backup_bytes(enc, "s3cret") == b"backup-bytes-secret"


def test_manual_send_skips_group_without_password(monkeypatch, tmp_path, session_factory):
    panel_archive = tmp_path / "panel.tar.gz"
    panel_archive.write_bytes(b"panel")
    sent: list[dict] = []
    notices: list[dict] = []

    monkeypatch.setattr(backups_router, "_get_backup_manager", lambda: FakeManager(panel_archive))
    monkeypatch.setattr(
        backups_router,
        "_telegram_credentials",
        lambda _db: ("tok", ["101", "-100999"]),
    )
    monkeypatch.setattr(
        backups_router,
        "send_tg_document",
        lambda token, chat_id, file_path, **kwargs: sent.append(
            {"chat_id": chat_id, "path": file_path, "kwargs": kwargs}
        )
        or True,
    )
    monkeypatch.setattr(
        admin_notify_service,
        "send_settings_change",
        lambda _db, **kwargs: notices.append(kwargs),
    )
    db = session_factory()

    backups_router._create_backup_with_optional_telegram(
        db,
        include_configs=False,
        include_antizapret_backup=False,
        include_awg2_backup=False,
        send_to_telegram=True,
        panel_caption_prefix="Бэкап AdminPanelAZ",
        az_caption_prefix="Бэкап AntiZapret",
    )

    assert [c["chat_id"] for c in sent] == ["101"]
    assert any(
        n.get("settings_key") == privacy.GROUP_PAUSE_SETTINGS_KEY
        or privacy.GROUP_PAUSE_MESSAGE in str(n.get("subject_name") or n.get("details") or "")
        for n in notices
    )


def test_manual_send_encrypts_when_password_set(monkeypatch, tmp_path, session_factory):
    panel_archive = tmp_path / "panel.tar.gz"
    panel_archive.write_bytes(b"panel-plain")
    sent: list[dict] = []

    monkeypatch.setattr(backups_router, "_get_backup_manager", lambda: FakeManager(panel_archive))
    monkeypatch.setattr(
        backups_router,
        "_telegram_credentials",
        lambda _db: ("tok", ["-100999"]),
    )
    monkeypatch.setattr(
        backups_router,
        "send_tg_document",
        lambda token, chat_id, file_path, **kwargs: sent.append(
            {
                "chat_id": chat_id,
                "path": Path(file_path),
                "data": Path(file_path).read_bytes(),
                "filename": kwargs.get("filename"),
            }
        )
        or True,
    )
    monkeypatch.setattr(
        privacy,
        "get_settings_secret_key",
        lambda: "test-secret-key-for-backup-password",
    )

    db = session_factory()
    privacy.set_backup_password(db, "backup-pass")
    db.commit()

    backups_router._create_backup_with_optional_telegram(
        db,
        include_configs=False,
        include_antizapret_backup=False,
        include_awg2_backup=False,
        send_to_telegram=True,
        panel_caption_prefix="Бэкап AdminPanelAZ",
        az_caption_prefix="Бэкап AntiZapret",
    )

    assert len(sent) == 1
    assert sent[0]["chat_id"] == "-100999"
    assert privacy.is_encrypted_backup_bytes(sent[0]["data"])
    assert privacy.decrypt_backup_bytes(sent[0]["data"], "backup-pass") == b"panel-plain"
    assert str(sent[0]["filename"] or sent[0]["path"].name).endswith(".enc")


def test_scheduled_send_skips_group_without_password(monkeypatch, tmp_path, session_factory):
    panel_archive = tmp_path / "panel.tar.gz"
    panel_archive.write_bytes(b"panel")
    sent: list[dict] = []

    class _Features:
        def is_enabled(self, _name):
            return True

    db = session_factory()
    for key, value in {
        "backup_auto_enabled": "true",
        "backup_telegram_enabled": "true",
        "backup_awg2_enabled": "false",
        "backup_az_enabled": "false",
        "telegram_bot_token": "tok",
    }.items():
        db.add(AppSetting(key=key, value=value))
    db.commit()
    db.close()

    monkeypatch.setattr(backup_scheduler, "SessionLocal", session_factory)
    monkeypatch.setattr(backup_scheduler, "BackupManager", lambda **_kw: FakeManager(panel_archive))
    monkeypatch.setattr(backup_scheduler, "collect_backup_config_contents", lambda _db: None)
    monkeypatch.setattr(backup_scheduler, "get_setting_chat_ids", lambda _get: ["101", "-100555"])
    monkeypatch.setattr(backup_scheduler, "_is_backups_enabled", lambda: True)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", lambda: _Features())
    monkeypatch.setattr(
        backup_scheduler,
        "send_tg_document",
        lambda token, chat_id, file_path, **kwargs: sent.append({"chat_id": chat_id}) or True,
    )
    monkeypatch.setattr(admin_notify_service, "send_settings_change", lambda *_a, **_k: None)

    backup_scheduler._run_auto_backup_once(
        app_root=tmp_path,
        backup_root=tmp_path / "backups",
        db_path=tmp_path / "panel.db",
        env_path=tmp_path / ".env",
        cidr_db_path=None,
    )

    assert [c["chat_id"] for c in sent] == ["101"]
