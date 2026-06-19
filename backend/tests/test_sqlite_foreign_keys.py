"""SQLite PRAGMA foreign_keys enforcement in test engines."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from tests.conftest import register_sqlite_pragmas


def test_test_engine_enables_foreign_keys(tmp_path):
    db_path = tmp_path / "fk_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    register_sqlite_pragmas(engine)

    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
