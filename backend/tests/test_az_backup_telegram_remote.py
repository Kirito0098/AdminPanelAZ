"""AntiZapret backups of a remote node reach Telegram: the archive is fetched from the node first."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AppSetting
from app.routers import backups as backups_router
from app.services import backup_scheduler
from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter

NODE_ONLY_PATH = "/nonexistent-node-dir/antizapret/backup-node-1.tar.gz"
ARCHIVE_BYTES = b"az-archive-from-node"


class FakeRemoteAdapter(RemoteNodeAdapter):
    def __init__(self, *, with_name: bool = True):
        self.downloads: list[str] = []
        self._with_name = with_name

    def create_antizapret_backup(self) -> dict[str, str]:
        if not self._with_name:
            return {"archive_path": NODE_ONLY_PATH}
        return {"archive_path": NODE_ONLY_PATH, "archive_name": "backup-node-1.tar.gz"}

    def download_antizapret_backup(self, archive_name: str) -> bytes:
        self.downloads.append(archive_name)
        return ARCHIVE_BYTES


class FakeManager:
    def __init__(self, panel_archive: Path):
        self._panel_archive = panel_archive

    def create_backup(self, **_kwargs):
        return {"file_name": self._panel_archive.name}

    def get_backup_path(self, _name):
        return self._panel_archive


@pytest.fixture()
def sent(monkeypatch):
    calls: list[dict] = []

    def fake_send(token, chat_id, file_path, *, caption="", run_async=True, filename=None):
        path = Path(file_path)
        calls.append(
            {
                "chat_id": chat_id,
                "path": path,
                "exists": path.is_file(),
                "data": path.read_bytes() if path.is_file() else None,
                "filename": filename,
                "caption": caption,
            }
        )
        return True

    monkeypatch.setattr(backups_router, "send_tg_document", fake_send)
    monkeypatch.setattr(backup_scheduler, "send_tg_document", fake_send)
    return calls


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


def _az_calls(calls):
    return [c for c in calls if "AntiZapret" in c["caption"]]


def test_remote_adapter_fetches_the_archive_into_a_temp_file_and_cleans_up():
    adapter = FakeRemoteAdapter()

    with adapter.antizapret_backup_file(adapter.create_antizapret_backup()) as path:
        assert path.read_bytes() == ARCHIVE_BYTES
        assert not str(path).startswith("/nonexistent-node-dir")
        kept = path

    assert adapter.downloads == ["backup-node-1.tar.gz"]
    assert not kept.exists()


def test_remote_adapter_falls_back_to_the_path_name_when_no_archive_name(tmp_path):
    adapter = FakeRemoteAdapter()

    with adapter.antizapret_backup_file({"archive_path": NODE_ONLY_PATH}) as path:
        assert path.read_bytes() == ARCHIVE_BYTES

    assert adapter.downloads == ["backup-node-1.tar.gz"]


def test_local_adapter_uses_the_archive_in_place(tmp_path):
    archive = tmp_path / "backup-local.tar.gz"
    archive.write_bytes(b"local")
    adapter = LocalNodeAdapter.__new__(LocalNodeAdapter)

    with adapter.antizapret_backup_file({"archive_path": str(archive), "archive_name": archive.name}) as path:
        assert path == archive

    assert archive.read_bytes() == b"local"


def test_manual_backup_sends_the_remote_node_archive(monkeypatch, tmp_path, sent, session_factory):
    adapter = FakeRemoteAdapter()
    panel_archive = tmp_path / "panel.tar.gz"
    panel_archive.write_bytes(b"panel")
    monkeypatch.setattr(backups_router, "_get_backup_manager", lambda: FakeManager(panel_archive))
    monkeypatch.setattr(backups_router, "get_active_adapter", lambda _db: adapter)
    monkeypatch.setattr(backups_router, "_telegram_credentials", lambda _db: ("tok", ["101", "202"]))
    db = session_factory()

    backups_router._create_backup_with_optional_telegram(
        db,
        include_configs=False,
        include_antizapret_backup=True,
        include_awg2_backup=False,
        send_to_telegram=True,
        panel_caption_prefix="Бэкап AdminPanelAZ",
        az_caption_prefix="Бэкап AntiZapret",
    )

    az = _az_calls(sent)
    assert [c["chat_id"] for c in az] == ["101", "202"]
    assert all(c["exists"] and c["data"] == ARCHIVE_BYTES for c in az)
    assert {c["filename"] for c in az} == {"backup-node-1.tar.gz"}
    assert az[0]["caption"] == "Бэкап AntiZapret: backup-node-1.tar.gz"
    assert adapter.downloads == ["backup-node-1.tar.gz"]
    assert not az[0]["path"].exists()


@pytest.mark.parametrize("with_name", [True, False])
def test_scheduled_backup_sends_the_remote_node_archive(monkeypatch, tmp_path, sent, session_factory, with_name):
    adapter = FakeRemoteAdapter(with_name=with_name)
    panel_archive = tmp_path / "panel.tar.gz"
    panel_archive.write_bytes(b"panel")

    class _Features:
        def is_enabled(self, _name):
            return True

    db = session_factory()
    for key, value in {
        "backup_auto_enabled": "true",
        "backup_telegram_enabled": "true",
        "backup_awg2_enabled": "false",
        "telegram_bot_token": "tok",
    }.items():
        db.add(AppSetting(key=key, value=value))
    db.commit()
    db.close()
    monkeypatch.setattr(backup_scheduler, "SessionLocal", session_factory)
    monkeypatch.setattr(backup_scheduler, "BackupManager", lambda **_kw: FakeManager(panel_archive))
    monkeypatch.setattr(backup_scheduler, "get_active_adapter", lambda _db: adapter)
    monkeypatch.setattr(backup_scheduler, "collect_backup_config_contents", lambda _db: None)
    monkeypatch.setattr(backup_scheduler, "get_setting_chat_ids", lambda _get: ["303"])
    monkeypatch.setattr(backup_scheduler, "_is_backups_enabled", lambda: True)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", lambda: _Features())

    backup_scheduler._run_auto_backup_once(
        app_root=tmp_path,
        backup_root=tmp_path / "backups",
        db_path=tmp_path / "panel.db",
        env_path=tmp_path / ".env",
        cidr_db_path=None,
    )

    az = _az_calls(sent)
    assert len(az) == 1
    assert az[0]["exists"] and az[0]["data"] == ARCHIVE_BYTES
    assert az[0]["filename"] == "backup-node-1.tar.gz"
    assert az[0]["caption"] == "Авто-бэкап AntiZapret: backup-node-1.tar.gz"
    assert not az[0]["path"].exists()
