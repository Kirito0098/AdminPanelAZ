"""Backup archives hold the panel DB and .env: only the owner may read them."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.backup_manager import BackupManager, _write_private_bytes, backup_meta_path
from app.services.security_bootstrap import restrict_backup_dir_permissions


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture(autouse=True)
def _default_umask():
    previous = os.umask(0o022)
    yield
    os.umask(previous)


def _manager(tmp_path: Path) -> BackupManager:
    tmp_path.mkdir(exist_ok=True)
    db = tmp_path / "adminpanel.db"
    sqlite3.connect(db).close()
    env = tmp_path / ".env"
    env.write_text("SECRET_KEY=x\n", encoding="utf-8")
    return BackupManager(app_root=tmp_path, backup_root=tmp_path / "backups", db_path=db, env_path=env)


def test_created_backup_is_owner_only(tmp_path: Path):
    mgr = _manager(tmp_path)
    created = mgr.create_backup(include_configs=True, config_contents={"include-hosts.txt": "a"}, awg2_archive=b"x")
    archive = tmp_path / "backups" / created["file_name"]

    assert _mode(tmp_path / "backups") == 0o700
    assert _mode(archive) == 0o600
    assert _mode(backup_meta_path(archive)) == 0o600


def test_existing_open_backup_dir_is_tightened_on_next_backup(tmp_path: Path):
    root = tmp_path / "backups"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    _manager(tmp_path).create_backup()
    assert _mode(root) == 0o700


def test_private_write_never_creates_readable_file(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(os, "fchmod", lambda fd, mode: None)
    target = tmp_path / "new.json"
    _write_private_bytes(target, b"{}")
    assert _mode(target) == 0o600


def test_private_write_tightens_existing_file(tmp_path: Path):
    target = tmp_path / "old.json"
    target.write_text("{}", encoding="utf-8")
    target.chmod(0o644)
    _write_private_bytes(target, b"{}")
    assert _mode(target) == 0o600
    assert target.read_bytes() == b"{}"


def test_uploaded_backup_is_owner_only(tmp_path: Path):
    source_mgr = _manager(tmp_path / "src")
    created = source_mgr.create_backup()
    upload = tmp_path / "upload.tar.gz"
    upload.write_bytes((tmp_path / "src" / "backups" / created["file_name"]).read_bytes())
    upload.chmod(0o644)

    mgr = _manager(tmp_path)
    imported = mgr.import_uploaded_backup(upload, original_name="adminpanelaz_from_pc.tar.gz")
    archive = tmp_path / "backups" / imported["file_name"]

    assert _mode(archive) == 0o600
    assert _mode(backup_meta_path(archive)) == 0o600


def test_startup_tightens_existing_backups_only(tmp_path: Path):
    root = tmp_path / "backups"
    root.mkdir()
    root.chmod(0o755)
    archive = root / "adminpanelaz_20260925_030022_708647.tar.gz"
    meta = root / "adminpanelaz_20260925_030022_708647.json"
    legacy_meta = root / "adminpanelaz_20260904_020022.tar.json"
    foreign = root / "README.txt"
    for path in (archive, meta, legacy_meta, foreign):
        path.write_text("x", encoding="utf-8")
        path.chmod(0o644)

    restrict_backup_dir_permissions(root)

    assert _mode(root) == 0o700
    assert _mode(archive) == 0o600
    assert _mode(meta) == 0o600
    assert _mode(legacy_meta) == 0o600
    assert _mode(foreign) == 0o644


def test_startup_ignores_missing_backup_dir(tmp_path: Path):
    restrict_backup_dir_permissions(tmp_path / "missing")
    assert not (tmp_path / "missing").exists()


def test_lifespan_tightens_backup_dir(tmp_path: Path, monkeypatch):
    from app import main

    root = tmp_path / "backups"
    root.mkdir()
    root.chmod(0o755)
    archive = root / "adminpanelaz_x.tar.gz"
    archive.write_text("x", encoding="utf-8")
    archive.chmod(0o644)

    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(database_url=f"sqlite:///{tmp_path / 'adminpanel.db'}", backup_root=root),
    )
    monkeypatch.setattr(main, "seed_database", lambda: None)
    monkeypatch.setattr(main, "restrict_sensitive_file_permissions", lambda _paths: None)
    monkeypatch.setattr(main, "spawn_background_tasks", lambda **_kw: {})
    monkeypatch.setattr(main, "run_leader_startup_actions", lambda: None)
    monkeypatch.setattr(main, "should_start_resource_monitor", lambda: False)

    async def scenario():
        async with main.lifespan(main.app):
            await asyncio.sleep(0)

    asyncio.run(scenario())
    assert _mode(root) == 0o700
    assert _mode(archive) == 0o600


def test_backup_root_chmod_failure_is_not_fatal(tmp_path: Path, monkeypatch, caplog):
    mgr = _manager(tmp_path)
    (tmp_path / "backups").mkdir(mode=0o755)
    (tmp_path / "backups").chmod(0o755)

    def deny(path, mode, *args, **kwargs):
        raise PermissionError("EPERM")

    monkeypatch.setattr("app.services.backup_manager.os.chmod", deny)
    assert mgr.list_backups() == []
    assert "backups" in caplog.text


def test_metadata_write_failure_leaves_no_partial_json(tmp_path: Path, monkeypatch):
    mgr = _manager(tmp_path)

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr("app.services.atomic_file.os.replace", boom)
    with pytest.raises(OSError):
        mgr.create_backup()
    root = tmp_path / "backups"
    assert not list(root.glob("*.json"))
    assert not [p for p in root.iterdir() if p.name.startswith(".tmp_")]
