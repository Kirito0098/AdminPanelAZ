"""Copies taken before a restore are listed, can be rolled back to and deleted."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.backup_manager import BackupManager


def _manager(tmp_path: Path) -> BackupManager:
    db = tmp_path / "adminpanel.db"
    env = tmp_path / ".env"
    env.write_text("X=1\n", encoding="utf-8")
    _db_with_row(db, 0)
    return BackupManager(app_root=tmp_path, backup_root=tmp_path / "backups", db_path=db, env_path=env)


def _db_with_row(path: Path, value: int) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS t(x INTEGER)")
    conn.execute("DELETE FROM t")
    conn.execute("INSERT INTO t VALUES (?)", (value,))
    conn.commit()
    conn.close()


def _row(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT x FROM t").fetchone()[0]
    finally:
        conn.close()


def _restore_over_live(mgr: BackupManager, *, archived: int, live: int, env: str) -> str:
    """Restore an archive holding ``archived`` over a live DB holding ``live``; return the copy id."""
    _db_with_row(mgr.db_path, archived)
    created = mgr.create_backup()
    _db_with_row(mgr.db_path, live)
    mgr.env_path.write_text(env, encoding="utf-8")
    applied = mgr.restore_backup(created["file_name"])
    return Path(applied["pre_restore_snapshot"]).name


def test_no_copies_before_first_restore(tmp_path: Path):
    assert _manager(tmp_path).list_pre_restore_snapshots() == []


def test_copy_is_listed_with_contents_size_and_time(tmp_path: Path):
    mgr = _manager(tmp_path)
    snapshot_id = _restore_over_live(mgr, archived=1, live=2, env="X=live\n")

    [entry] = mgr.list_pre_restore_snapshots()

    folder = tmp_path / "backups" / BackupManager.PRE_RESTORE_DIR / snapshot_id
    assert entry["snapshot_id"] == snapshot_id
    assert sorted(entry["components"]) == ["db", "env"]
    assert entry["size_bytes"] == sum(p.stat().st_size for p in folder.iterdir())
    date, clock, _micro = snapshot_id.split("_")
    assert entry["created_at"] == f"{date[:4]}-{date[4:6]}-{date[6:]}T{clock[:2]}:{clock[2:4]}:{clock[4:]}Z"


def test_copies_are_listed_newest_first_and_foreign_entries_ignored(tmp_path: Path):
    mgr = _manager(tmp_path)
    first = _restore_over_live(mgr, archived=1, live=2, env="X=a\n")
    second = _restore_over_live(mgr, archived=1, live=3, env="X=b\n")
    root = tmp_path / "backups" / BackupManager.PRE_RESTORE_DIR
    (root / "notes").mkdir()
    (root / "stray.txt").write_text("x", encoding="utf-8")

    assert [e["snapshot_id"] for e in mgr.list_pre_restore_snapshots()] == [second, first]


def test_rollback_brings_back_files_replaced_by_the_restore(tmp_path: Path):
    mgr = _manager(tmp_path)
    snapshot_id = _restore_over_live(mgr, archived=1, live=2, env="X=live\n")
    assert _row(mgr.db_path) == 1

    applied = mgr.apply_restore_payload(mgr.load_pre_restore_payload(snapshot_id))

    assert _row(mgr.db_path) == 2
    assert mgr.env_path.read_text(encoding="utf-8") == "X=live\n"
    assert sorted(applied["restored"]) == ["db", "env"]
    undo = Path(applied["pre_restore_snapshot"])
    assert undo.name != snapshot_id
    assert _row(undo / "adminpanel.db") == 1, "the rollback itself can be undone"


def test_rollback_to_oldest_kept_copy_does_not_delete_it(tmp_path: Path):
    mgr = _manager(tmp_path)
    ids = [_restore_over_live(mgr, archived=1, live=live, env=f"X={live}\n") for live in (2, 3, 4)]
    assert len(ids) == BackupManager.PRE_RESTORE_KEEP

    applied = mgr.apply_restore_payload(mgr.load_pre_restore_payload(ids[0]))

    assert _row(mgr.db_path) == 2
    kept = [e["snapshot_id"] for e in mgr.list_pre_restore_snapshots()]
    assert ids[0] in kept, "the copy just rolled back to stays available"
    assert Path(applied["pre_restore_snapshot"]).name in kept


def test_rollback_refuses_damaged_copy_without_touching_live_files(tmp_path: Path):
    mgr = _manager(tmp_path)
    snapshot_id = _restore_over_live(mgr, archived=1, live=2, env="X=live\n")
    folder = tmp_path / "backups" / BackupManager.PRE_RESTORE_DIR / snapshot_id
    (folder / "adminpanel.db").write_bytes(b"garbage")
    live_before = mgr.db_path.read_bytes()

    with pytest.raises(HTTPException) as exc:
        mgr.load_pre_restore_payload(snapshot_id)

    assert exc.value.status_code == 400
    assert mgr.db_path.read_bytes() == live_before


@pytest.mark.parametrize("bad_id", ["../backups", "20260101", ".", "20260926_101010_000000/../x"])
def test_invalid_copy_id_is_not_found(tmp_path: Path, bad_id: str):
    mgr = _manager(tmp_path)
    _restore_over_live(mgr, archived=1, live=2, env="X=live\n")
    for action in (mgr.load_pre_restore_payload, mgr.delete_pre_restore_snapshot):
        with pytest.raises(HTTPException) as exc:
            action(bad_id)
        assert exc.value.status_code == 404


def test_copy_id_with_path_suffix_is_not_found(tmp_path: Path):
    """A valid id prefix followed by path segments still resolves to an existing folder."""
    mgr = _manager(tmp_path)
    snapshot_id = _restore_over_live(mgr, archived=1, live=2, env="X=live\n")
    with pytest.raises(HTTPException) as exc:
        mgr.delete_pre_restore_snapshot(f"{snapshot_id}/../{snapshot_id}")
    assert exc.value.status_code == 404
    assert [e["snapshot_id"] for e in mgr.list_pre_restore_snapshots()] == [snapshot_id]


def test_missing_copy_is_not_found(tmp_path: Path):
    mgr = _manager(tmp_path)
    with pytest.raises(HTTPException) as exc:
        mgr.load_pre_restore_payload("20260926_101010_000000")
    assert exc.value.status_code == 404


def test_delete_removes_only_that_copy(tmp_path: Path):
    mgr = _manager(tmp_path)
    first = _restore_over_live(mgr, archived=1, live=2, env="X=a\n")
    second = _restore_over_live(mgr, archived=1, live=3, env="X=b\n")

    mgr.delete_pre_restore_snapshot(first)

    assert [e["snapshot_id"] for e in mgr.list_pre_restore_snapshots()] == [second]
    assert not (tmp_path / "backups" / BackupManager.PRE_RESTORE_DIR / first).exists()
