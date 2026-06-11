"""Tests for CSV staging and native SQLite CIDR import."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.services.cidr.pipeline.cidr_csv_import import (
    cleanup_staging_csv,
    import_provider_cidr_csv,
    staging_csv_path,
    staging_csv_tmp_path,
    write_provider_cidr_csv,
)


def _create_provider_cidr_table(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE provider_cidr (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_key VARCHAR(64) NOT NULL,
                cidr VARCHAR(50) NOT NULL,
                region_scope VARCHAR(64),
                country_codes VARCHAR(255),
                refreshed_at DATETIME,
                UNIQUE (provider_key, cidr)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _seed_provider_rows(db_path: Path, provider_key: str, cidrs: list[str]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        for cidr in cidrs:
            conn.execute(
                "INSERT INTO provider_cidr (provider_key, cidr) VALUES (?, ?)",
                (provider_key, cidr),
            )
        conn.commit()
    finally:
        conn.close()


class CidrCsvImportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.staging_dir = Path(self.temp_dir.name) / "staging"
        self.staging_dir.mkdir()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        _create_provider_cidr_table(self.db_path)
        self.settings_patch = patch("app.services.cidr.pipeline.cidr_csv_import.get_settings")
        self.mock_settings = self.settings_patch.start()
        self.mock_settings.return_value.cidr_db_staging_dir = Path("data/cidr/staging")
        self.mock_settings.return_value.cidr_db_csv_import_batch = 1000
        self.mock_settings.return_value.cidr_db_csv_import_chunk_rows = 0
        self.mock_settings.return_value.cidr_db_keep_staging_csv = False
        self.staging_patch = patch(
            "app.services.cidr.pipeline.cidr_csv_import.get_staging_dir",
            return_value=self.staging_dir,
        )
        self.staging_patch.start()

    def tearDown(self):
        self.staging_patch.stop()
        self.settings_patch.stop()
        self.temp_dir.cleanup()

    def test_write_and_import_roundtrip(self):
        items = [
            {"cidr": "1.2.3.0/24", "region": "eu", "countries": ["DE", "FR"]},
            {"cidr": "5.6.7.0/24", "region": None, "countries": None},
        ]
        csv_path, total = write_provider_cidr_csv("akamai-ips.txt", items)
        self.assertEqual(total, 2)
        self.assertTrue(csv_path.is_file())
        self.assertFalse(staging_csv_tmp_path("akamai-ips.txt").exists())

        imported = import_provider_cidr_csv(self.db_path, "akamai-ips.txt", csv_path, total_rows=total)
        self.assertEqual(imported, 2)
        self.assertFalse(csv_path.exists())

        conn = sqlite3.connect(self.db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM provider_cidr WHERE provider_key = ?",
                ("akamai-ips.txt",),
            ).fetchone()[0]
            self.assertEqual(count, 2)
            row = conn.execute(
                "SELECT region_scope, country_codes FROM provider_cidr WHERE cidr = ?",
                ("1.2.3.0/24",),
            ).fetchone()
            self.assertEqual(row, ("eu", "DE,FR"))
        finally:
            conn.close()

    def test_dedupe_on_write(self):
        items = [
            {"cidr": "10.0.0.0/8", "region": None, "countries": None},
            {"cidr": "10.0.0.0/8", "region": "x", "countries": ["US"]},
        ]
        _, total = write_provider_cidr_csv("cloudflare-ips.txt", items)
        self.assertEqual(total, 1)

    def test_import_replaces_existing_provider_rows(self):
        _seed_provider_rows(self.db_path, "cdn77-ips.txt", ["9.9.9.0/24", "8.8.8.0/24"])
        csv_path, total = write_provider_cidr_csv(
            "cdn77-ips.txt",
            [{"cidr": "1.1.1.0/24", "region": None, "countries": None}],
        )
        import_provider_cidr_csv(
            self.db_path,
            "cdn77-ips.txt",
            csv_path,
            total_rows=total,
            keep_csv=True,
        )
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT cidr FROM provider_cidr WHERE provider_key = ? ORDER BY cidr",
                ("cdn77-ips.txt",),
            ).fetchall()
            self.assertEqual(rows, [("1.1.1.0/24",)])
        finally:
            conn.close()

    def test_chunked_import_commits_incrementally(self):
        self.mock_settings.return_value.cidr_db_csv_import_batch = 500
        self.mock_settings.return_value.cidr_db_csv_import_chunk_rows = 1000
        items = [{"cidr": f"10.{i // 256}.{i % 256}.0/24", "region": None, "countries": None} for i in range(2500)]
        csv_path, total = write_provider_cidr_csv("heavy.txt", items)
        imported = import_provider_cidr_csv(
            self.db_path,
            "heavy.txt",
            csv_path,
            total_rows=total,
            keep_csv=True,
        )
        self.assertEqual(imported, 2500)
        conn = sqlite3.connect(self.db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM provider_cidr WHERE provider_key = ?",
                ("heavy.txt",),
            ).fetchone()[0]
            self.assertEqual(count, 2500)
        finally:
            conn.close()

    def test_keep_staging_csv_when_configured(self):
        csv_path, total = write_provider_cidr_csv(
            "keep-me.txt",
            [{"cidr": "2.2.2.0/24", "region": None, "countries": None}],
        )
        self.mock_settings.return_value.cidr_db_keep_staging_csv = True
        import_provider_cidr_csv(self.db_path, "keep-me.txt", csv_path, total_rows=total)
        self.assertTrue(staging_csv_path("keep-me.txt").exists())

    def test_import_failure_keeps_csv(self):
        csv_path, total = write_provider_cidr_csv(
            "fail.txt",
            [{"cidr": "3.3.3.0/24", "region": None, "countries": None}],
        )
        bad_db = Path(self.temp_dir.name) / "missing-table.db"
        bad_db.touch()
        with self.assertRaises(sqlite3.OperationalError):
            import_provider_cidr_csv(bad_db, "fail.txt", csv_path, total_rows=total)
        self.assertTrue(csv_path.exists())

    def test_cleanup_staging_csv(self):
        write_provider_cidr_csv(
            "cleanup.txt",
            [{"cidr": "4.4.4.0/24", "region": None, "countries": None}],
        )
        tmp = staging_csv_tmp_path("cleanup.txt")
        tmp.write_text("partial", encoding="utf-8")
        cleanup_staging_csv("cleanup.txt")
        self.assertFalse(staging_csv_path("cleanup.txt").exists())
        self.assertFalse(tmp.exists())

    def test_cleanup_removes_stale_tmp_files(self):
        stale = self.staging_dir / "stale.csv.tmp"
        stale.write_text("x", encoding="utf-8")
        cleanup_staging_csv()
        self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
