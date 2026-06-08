"""BackupManager service tests — adapted from AdminAntizapret backup manager tests."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path

from app.services.backup_manager import BackupManager


def _write_test_sqlite(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT NOT NULL)")
        conn.execute("INSERT INTO user (id, username) VALUES (1, 'testadmin')")
        conn.commit()
    finally:
        conn.close()


class BackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="backup-manager-test-"))
        self.app_root = self.tmp_dir / "app"
        self.backup_root = self.tmp_dir / "backups"
        backend = self.app_root / "backend"
        data_dir = backend / "data"
        data_dir.mkdir(parents=True)
        self.db_path = data_dir / "adminpanel.db"
        self.env_path = backend / ".env"
        _write_test_sqlite(self.db_path)
        self.env_path.write_text("SECRET_KEY=abc\n", encoding="utf-8")
        self.manager = BackupManager(
            app_root=self.app_root,
            backup_root=self.backup_root,
            db_path=self.db_path,
            env_path=self.env_path,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_backup_includes_db_and_env(self):
        result = self.manager.create_backup()
        archive_path = Path(result["file_path"])
        self.assertTrue(archive_path.is_file())
        self.assertIn("db", result["components"])
        self.assertIn("env", result["components"])
        with tarfile.open(archive_path, "r:gz") as tar:
            names = {m.name for m in tar.getmembers()}
        self.assertIn("data/adminpanel.db", names)
        self.assertIn("env/.env", names)

    def test_list_backups_reads_metadata(self):
        self.manager.create_backup()
        backups = self.manager.list_backups()
        self.assertEqual(len(backups), 1)
        self.assertIn("db", backups[0]["components"])
        meta_path = self.backup_root / backups[0]["file_name"].replace(".tar.gz", ".tar.json")
        self.assertTrue(meta_path.is_file())
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertIn("created_at", meta)

    def test_restore_backup_restores_db_and_env(self):
        created = self.manager.create_backup()
        self.db_path.write_bytes(b"")
        self.env_path.write_text("CORRUPT=1\n", encoding="utf-8")

        restored = self.manager.restore_backup(created["file_name"])
        self.assertEqual(set(restored["restored"]), {"db", "env"})
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT username FROM user WHERE id=1").fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], "testadmin")
        self.assertIn("SECRET_KEY=abc", self.env_path.read_text(encoding="utf-8"))

    def test_delete_backup_removes_archive_and_metadata(self):
        created = self.manager.create_backup()
        file_name = created["file_name"]
        self.manager.delete_backup(file_name)
        self.assertFalse((self.backup_root / file_name).exists())
        self.assertFalse((self.backup_root / file_name.replace(".tar.gz", ".tar.json")).exists())

    def test_enforce_retention_keeps_latest_five(self):
        for idx in range(7):
            self.manager.create_backup()
            archives = sorted(self.backup_root.glob("*.tar.gz"), key=lambda p: p.name)
            if archives:
                archives[-1].touch()
        listed = self.manager.list_backups()
        self.assertLessEqual(len(listed), 5)
