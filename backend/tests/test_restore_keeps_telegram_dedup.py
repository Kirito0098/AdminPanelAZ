"""A restored DB must remember update ids claimed after the backup: a redelivered bot restore must not run twice."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.database import Base
from app.models import TelegramProcessedUpdate
from app.services import backup_manager as backup_manager_module
from app.services import telegram_update_dedup
from app.services.backup_manager import BackupManager
from app.services.telegram_update_dedup import claim_telegram_update


def _session(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)
    return engine, sessionmaker(bind=engine)()


def _full_db(db_path: Path, update_ids: list[int]) -> None:
    db_path.unlink(missing_ok=True)
    engine, session = _session(db_path)
    try:
        Base.metadata.create_all(engine)
        for update_id in update_ids:
            session.add(TelegramProcessedUpdate(update_id=update_id, received_at=datetime.utcnow()))
        session.commit()
    finally:
        session.close()
        engine.dispose()


def _bare_db(db_path: Path) -> None:
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t(x INTEGER)")
    conn.commit()
    conn.close()


def _manager(tmp_path: Path) -> BackupManager:
    env = tmp_path / ".env"
    env.write_text("X=1\n", encoding="utf-8")
    return BackupManager(
        app_root=tmp_path,
        backup_root=tmp_path / "backups",
        db_path=tmp_path / "adminpanel.db",
        env_path=env,
    )


def _update_ids(db_path: Path) -> set[int]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT update_id FROM telegram_processed_updates")}
    finally:
        conn.close()


def _tables_and_indexes(db_path: Path) -> set[tuple[str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            (row[0], row[1])
            for row in conn.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        }
    finally:
        conn.close()


def _claim(db_path: Path, update_id: int) -> bool:
    engine, session = _session(db_path)
    try:
        return claim_telegram_update(session, update_id)
    finally:
        session.close()
        engine.dispose()


def test_restore_keeps_update_ids_claimed_after_the_backup(tmp_path: Path):
    mgr = _manager(tmp_path)
    _full_db(mgr.db_path, [7, 10])
    archive = mgr.create_backup()["file_name"]
    # 42 is the "restore" callback being processed; 7 is in both databases.
    _full_db(mgr.db_path, [7, 42])

    mgr.restore_backup(archive)

    assert _update_ids(mgr.db_path) == {7, 10, 42}
    assert _claim(mgr.db_path, 42) is False
    assert _claim(mgr.db_path, 43) is True


def test_restore_keeps_received_at_of_carried_rows(tmp_path: Path):
    mgr = _manager(tmp_path)
    _full_db(mgr.db_path, [])
    archive = mgr.create_backup()["file_name"]
    engine, session = _session(mgr.db_path)
    old = datetime.utcnow() - timedelta(days=1, hours=3)
    session.add(TelegramProcessedUpdate(update_id=42, received_at=old))
    session.commit()
    session.close()
    engine.dispose()

    mgr.restore_backup(archive)

    engine, session = _session(mgr.db_path)
    try:
        assert session.get(TelegramProcessedUpdate, 42).received_at == old
    finally:
        session.close()
        engine.dispose()


def test_restore_of_archive_without_the_table_creates_it_like_create_all(tmp_path: Path):
    mgr = _manager(tmp_path)
    _bare_db(mgr.db_path)
    archive = mgr.create_backup()["file_name"]
    _full_db(mgr.db_path, [42])

    mgr.restore_backup(archive)

    assert _update_ids(mgr.db_path) == {42}
    reference = tmp_path / "reference.db"
    _full_db(reference, [])
    dedup_objects = {obj for obj in _tables_and_indexes(reference) if "telegram_processed_updates" in obj[1]}
    assert dedup_objects <= _tables_and_indexes(mgr.db_path)
    assert ("table", "t") in _tables_and_indexes(mgr.db_path)


def test_restore_over_live_db_without_the_table_leaves_restored_db_as_is(tmp_path: Path, caplog):
    mgr = _manager(tmp_path)
    _bare_db(mgr.db_path)
    archive = mgr.create_backup()["file_name"]

    with caplog.at_level(logging.ERROR):
        mgr.restore_backup(archive)

    assert _tables_and_indexes(mgr.db_path) == {("table", "t")}
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_restore_over_empty_table_leaves_restored_db_as_is(tmp_path: Path, caplog):
    mgr = _manager(tmp_path)
    _bare_db(mgr.db_path)
    archive = mgr.create_backup()["file_name"]
    _full_db(mgr.db_path, [])

    with caplog.at_level(logging.ERROR):
        mgr.restore_backup(archive)

    assert _tables_and_indexes(mgr.db_path) == {("table", "t")}
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_restore_succeeds_when_carrying_update_ids_fails(tmp_path: Path, monkeypatch, caplog):
    mgr = _manager(tmp_path)
    _full_db(mgr.db_path, [10])
    archive = mgr.create_backup()["file_name"]
    _full_db(mgr.db_path, [42])

    def _boom(source: Path, target: Path) -> int:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(telegram_update_dedup, "carry_over_processed_updates", _boom)
    with caplog.at_level(logging.ERROR, logger=backup_manager_module.logger.name):
        result = mgr.restore_backup(archive)

    assert result["file_name"] == archive
    assert _update_ids(mgr.db_path) == {10}
    assert "update" in caplog.text.lower()


def test_rollback_to_pre_restore_copy_keeps_ids_claimed_after_the_restore(tmp_path: Path):
    mgr = _manager(tmp_path)
    _full_db(mgr.db_path, [10])
    archive = mgr.create_backup()["file_name"]
    _full_db(mgr.db_path, [42])
    snapshot_id = Path(mgr.restore_backup(archive)["pre_restore_snapshot"]).name
    assert _claim(mgr.db_path, 43) is True

    mgr.apply_restore_payload(mgr.load_pre_restore_payload(snapshot_id))

    assert _update_ids(mgr.db_path) == {10, 42, 43}


def test_env_only_restore_does_not_touch_the_db(tmp_path: Path, caplog):
    mgr = _manager(tmp_path)
    _full_db(mgr.db_path, [42])
    before = mgr.db_path.read_bytes()

    with caplog.at_level(logging.ERROR):
        mgr.apply_restore_payload({"restored": ["env"], "file_name": "x", "_files": {"env": b"X=2\n"}})

    assert mgr.db_path.read_bytes() == before
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_restore_without_files_skips_the_carry_over(tmp_path: Path):
    mgr = _manager(tmp_path)
    _full_db(mgr.db_path, [42])

    result = mgr.apply_restore_payload({"restored": [], "file_name": "x", "_files": {}})

    assert "pre_restore_snapshot" not in result
    assert _update_ids(mgr.db_path) == {42}
