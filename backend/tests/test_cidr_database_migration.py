"""Tests for one-time provider_cidr migration from adminpanel.db to cidr.db."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.cidr_database import CidrBase, run_cidr_db_migrations
from app.cidr_models import ProviderCidr
from app.database import Base


def _create_main_provider_cidr_table(db_path: Path) -> None:
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
        conn.execute(
            "INSERT INTO provider_cidr (provider_key, cidr, refreshed_at) VALUES ('test-provider', '1.2.3.0/24', '2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO provider_cidr (provider_key, cidr, refreshed_at) VALUES ('test-provider', '4.5.6.0/24', '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()


class CidrDatabaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.main_path = Path(self.temp_dir.name) / "adminpanel.db"
        self.cidr_path = Path(self.temp_dir.name) / "cidr" / "cidr.db"
        self.cidr_path.parent.mkdir(parents=True, exist_ok=True)
        _create_main_provider_cidr_table(self.main_path)

        self.main_engine = create_engine(
            f"sqlite:///{self.main_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.main_engine)

        self.cidr_engine = create_engine(
            f"sqlite:///{self.cidr_path}",
            connect_args={"check_same_thread": False},
        )

        self.main_patch = patch("app.database.engine", self.main_engine)
        self.cidr_patch = patch("app.cidr_database.cidr_engine", self.cidr_engine)
        self.main_path_patch = patch(
            "app.cidr_database.resolve_cidr_db_path",
            return_value=self.cidr_path,
        )
        self.main_db_path_patch = patch(
            "app.database.resolve_main_db_path",
            return_value=self.main_path,
        )
        self.main_patch.start()
        self.cidr_patch.start()
        self.main_path_patch.start()
        self.main_db_path_patch.start()

    def tearDown(self):
        self.main_db_path_patch.stop()
        self.main_path_patch.stop()
        self.cidr_patch.stop()
        self.main_patch.stop()
        self.cidr_engine.dispose()
        self.main_engine.dispose()
        self.temp_dir.cleanup()

    def test_migrates_rows_and_drops_main_table(self):
        run_cidr_db_migrations()

        cidr_inspector = inspect(self.cidr_engine)
        self.assertIn("provider_cidr", cidr_inspector.get_table_names())
        with self.cidr_engine.connect() as conn:
            migrated_count = int(conn.execute(text("SELECT COUNT(*) FROM provider_cidr")).scalar() or 0)
        self.assertEqual(migrated_count, 2)

        main_inspector = inspect(self.main_engine)
        self.assertNotIn("provider_cidr", main_inspector.get_table_names())

    def test_migration_is_idempotent(self):
        run_cidr_db_migrations()
        run_cidr_db_migrations()

        with self.cidr_engine.connect() as conn:
            migrated_count = int(conn.execute(text("SELECT COUNT(*) FROM provider_cidr")).scalar() or 0)
        self.assertEqual(migrated_count, 2)

    def test_cidr_base_creates_provider_cidr_schema(self):
        CidrBase.metadata.create_all(bind=self.cidr_engine)
        Session = sessionmaker(bind=self.cidr_engine)
        db = Session()
        try:
            db.add(ProviderCidr(provider_key="p1", cidr="10.0.0.0/8"))
            db.commit()
            self.assertEqual(db.query(ProviderCidr).count(), 1)
        finally:
            db.close()
