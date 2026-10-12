"""Web/API restore, download and delete only take archives from the backup directory."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.backup_manager import BackupManager


def _manager(tmp_path: Path) -> BackupManager:
    db = tmp_path / "adminpanel.db"
    sqlite3.connect(db).close()
    env = tmp_path / ".env"
    env.write_text("X=1\n", encoding="utf-8")
    return BackupManager(app_root=tmp_path, backup_root=tmp_path / "backups", db_path=db, env_path=env)


def _move_out(mgr: BackupManager, directory: Path) -> Path:
    name = mgr.create_backup()["file_name"]
    directory.mkdir()
    target = directory / name
    shutil.move(str(mgr.backup_root / name), str(target))
    return target


def _status(call) -> int:
    with pytest.raises(HTTPException) as exc:
        call()
    return exc.value.status_code


def test_restore_rejects_absolute_path_outside_backup_dir(tmp_path: Path):
    mgr = _manager(tmp_path)
    outside = _move_out(mgr, tmp_path / "outside")

    assert _status(lambda: mgr.load_restore_payload(str(outside))) == 400


def test_download_and_delete_reject_absolute_path(tmp_path: Path):
    mgr = _manager(tmp_path)
    outside = _move_out(mgr, tmp_path / "outside")

    assert _status(lambda: mgr.get_backup_path(str(outside))) == 400
    assert _status(lambda: mgr.delete_backup(str(outside))) == 400
    assert outside.exists()


def test_symlink_to_sibling_directory_is_rejected(tmp_path: Path):
    mgr = _manager(tmp_path)
    outside = _move_out(mgr, tmp_path / "backups-old")
    link = mgr.backup_root / "adminpanelaz_link.tar.gz"
    link.symlink_to(outside)

    assert _status(lambda: mgr.load_restore_payload(link.name)) == 400


def test_cli_may_restore_from_absolute_path(tmp_path: Path):
    mgr = _manager(tmp_path)
    outside = _move_out(mgr, tmp_path / "outside")

    payload = mgr.load_restore_payload(str(outside), allow_absolute_path=True)

    assert "env" in payload["restored"]


def test_archive_name_from_backup_dir_still_restores(tmp_path: Path):
    mgr = _manager(tmp_path)
    name = mgr.create_backup()["file_name"]

    assert "env" in mgr.load_restore_payload(name)["restored"]
