from pathlib import Path

import sqlite3
import tarfile

from app.services.backup_manager import BackupManager, backup_meta_path


def _manager(tmp_path: Path, **kwargs) -> BackupManager:
    db = tmp_path / "adminpanel.db"
    sqlite3.connect(db).close()
    env = tmp_path / ".env"
    env.write_text("X=1\n", encoding="utf-8")
    return BackupManager(
        app_root=tmp_path,
        backup_root=tmp_path / "backups",
        db_path=db,
        env_path=env,
        **kwargs,
    )


def test_backup_meta_path_strips_tar_gz():
    assert backup_meta_path(Path("adminpanelaz_1.tar.gz")).name == "adminpanelaz_1.json"


def test_create_backup_writes_json_sidecar_not_tar_json(tmp_path: Path):
    result = _manager(tmp_path).create_backup()
    archive = tmp_path / "backups" / result["file_name"]
    canonical = backup_meta_path(archive)
    assert canonical.is_file()
    assert canonical.name.endswith(".json")
    assert not canonical.name.endswith(".tar.json")
    assert not archive.with_suffix(".json").exists()


def test_create_backup_honors_retention(tmp_path: Path):
    mgr = _manager(tmp_path)
    created = [mgr.create_backup(retention=3)["file_name"] for _ in range(5)]
    leftover = sorted(p.name for p in (tmp_path / "backups").glob("*.tar.gz"))
    assert len(leftover) == 3
    assert set(leftover) == set(created[-3:])
    leftover_meta = list((tmp_path / "backups").glob("*.json"))
    assert len(leftover_meta) == 3
    assert not list((tmp_path / "backups").glob("*.tar.json"))


def test_create_backup_includes_cidr_db(tmp_path: Path):
    cidr = tmp_path / "cidr.db"
    sqlite3.connect(cidr).close()
    result = _manager(tmp_path, cidr_db_path=cidr).create_backup()
    with tarfile.open(tmp_path / "backups" / result["file_name"], "r:gz") as tar:
        assert "data/cidr/cidr.db" in tar.getnames()
    assert "cidr_db" in result["components"]


def test_restore_backup_writes_cidr_db(tmp_path: Path):
    cidr = tmp_path / "cidr.db"
    conn = sqlite3.connect(cidr)
    conn.execute("CREATE TABLE t(x INTEGER)")
    conn.execute("INSERT INTO t VALUES (7)")
    conn.commit()
    conn.close()
    mgr = _manager(tmp_path, cidr_db_path=cidr)
    created = mgr.create_backup()
    cidr.unlink()
    restored_cidr = tmp_path / "restored-cidr.db"
    mgr.cidr_db_path = restored_cidr
    mgr.restore_backup(created["file_name"])
    rows = sqlite3.connect(restored_cidr).execute("SELECT x FROM t").fetchall()
    assert rows == [(7,)]


def test_create_backup_captures_wal_committed_rows(tmp_path: Path):
    db = tmp_path / "adminpanel.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE t(x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    env = tmp_path / ".env"
    env.write_text("X=1\n", encoding="utf-8")
    mgr = BackupManager(
        app_root=tmp_path,
        backup_root=tmp_path / "backups",
        db_path=db,
        env_path=env,
    )
    result = mgr.create_backup()
    restored = tmp_path / "restored.db"
    mgr.db_path = restored
    mgr.restore_backup(result["file_name"])
    conn.close()
    rows = sqlite3.connect(restored).execute("SELECT x FROM t").fetchall()
    assert rows == [(42,)]


def test_create_backup_packs_routing_lists(tmp_path: Path):
    result = _manager(tmp_path).create_backup(
        include_configs=True,
        config_contents={"include-hosts.txt": "example.com\n", "skip-me.txt": "nope"},
    )
    with tarfile.open(tmp_path / "backups" / result["file_name"], "r:gz") as tar:
        names = tar.getnames()
        assert "antizapret/config/include-hosts.txt" in names
        assert "antizapret/config/skip-me.txt" not in names
        payload = tar.extractfile("antizapret/config/include-hosts.txt")
        assert payload is not None
        assert payload.read() == b"example.com\n"
    assert "configs" in result["components"]


def test_restore_backup_returns_config_contents(tmp_path: Path):
    mgr = _manager(tmp_path)
    created = mgr.create_backup(
        include_configs=True,
        config_contents={"include-hosts.txt": "example.com\n"},
    )
    restored = mgr.restore_backup(created["file_name"])
    assert "configs" in restored["restored"]
    assert restored["configs"]["include-hosts.txt"] == "example.com\n"


def test_create_backup_packs_awg2_overlay(tmp_path: Path):
    result = _manager(tmp_path).create_backup(awg2_archive=b"narrow-awg2-bytes")
    with tarfile.open(tmp_path / "backups" / result["file_name"], "r:gz") as tar:
        extracted = tar.extractfile(BackupManager.AWG2_ARCHIVE_MEMBER)
        assert extracted is not None
        assert extracted.read() == b"narrow-awg2-bytes"
    assert "awg2" in result["components"]


def test_load_restore_payload_keeps_awg2_bytes_without_writing_live_files(tmp_path: Path):
    mgr = _manager(tmp_path)
    created = mgr.create_backup(awg2_archive=b"overlay-payload")
    payload = mgr.load_restore_payload(created["file_name"])
    assert "awg2" in payload["restored"]
    assert payload["_files"]["awg2"] == b"overlay-payload"
    assert not (tmp_path / "az-awg2-backup.tar.gz").exists()
    applied = mgr.apply_restore_payload(payload)
    assert "awg2" in applied["restored"]
    assert not (tmp_path / "az-awg2-backup.tar.gz").exists()


def test_inspect_backup_archive_lists_awg2_component(tmp_path: Path):
    mgr = _manager(tmp_path)
    created = mgr.create_backup(awg2_archive=b"overlay-payload")
    inspected = mgr.inspect_backup_archive(tmp_path / "backups" / created["file_name"])
    assert "awg2" in inspected["components"]


def test_load_restore_payload_does_not_write_db_until_apply(tmp_path: Path):
    mgr = _manager(tmp_path)
    conn = sqlite3.connect(mgr.db_path)
    conn.execute("CREATE TABLE t(x INTEGER)")
    conn.execute("INSERT INTO t VALUES (9)")
    conn.commit()
    conn.close()
    created = mgr.create_backup()
    archive = tmp_path / "backups" / created["file_name"]
    with tarfile.open(archive, "r:gz") as tar:
        extracted = tar.extractfile("data/adminpanel.db")
        assert extracted is not None
        archived_db = extracted.read()
    mgr.db_path.write_bytes(b"CHANGED-LIVE-DB")
    payload = mgr.load_restore_payload(created["file_name"])
    assert mgr.db_path.read_bytes() == b"CHANGED-LIVE-DB"
    applied = mgr.apply_restore_payload(payload)
    assert "db" in applied["restored"]
    assert mgr.db_path.read_bytes() == archived_db
    rows = sqlite3.connect(mgr.db_path).execute("SELECT x FROM t").fetchall()
    assert rows == [(9,)]


def _db_with_row(path: Path, value: int) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS t(x INTEGER)")
    conn.execute("DELETE FROM t")
    conn.execute("INSERT INTO t VALUES (?)", (value,))
    conn.commit()
    conn.close()


def _archive_with_db(tmp_path: Path, db_bytes: bytes, name: str = "adminpanelaz_bad.tar.gz") -> str:
    backups = tmp_path / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    member = tmp_path / "member.db"
    member.write_bytes(db_bytes)
    with tarfile.open(backups / name, "w:gz") as tar:
        tar.add(member, arcname="data/adminpanel.db")
    member.unlink()
    return name


def test_restore_rejects_archive_db_that_is_not_sqlite(tmp_path: Path):
    import pytest
    from fastapi import HTTPException

    mgr = _manager(tmp_path)
    _db_with_row(mgr.db_path, 1)
    live_before = mgr.db_path.read_bytes()
    name = _archive_with_db(tmp_path, b"not a database at all")

    with pytest.raises(HTTPException) as exc:
        mgr.load_restore_payload(name)

    assert exc.value.status_code == 400
    assert mgr.db_path.read_bytes() == live_before


def test_restore_rejects_truncated_archive_db(tmp_path: Path):
    import pytest
    from fastapi import HTTPException

    mgr = _manager(tmp_path)
    source = tmp_path / "source.db"
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE big(x TEXT)")
    conn.executemany("INSERT INTO big VALUES (?)", [("y" * 500,) for _ in range(400)])
    conn.commit()
    conn.close()
    data = source.read_bytes()
    name = _archive_with_db(tmp_path, data[: len(data) // 2])

    with pytest.raises(HTTPException) as exc:
        mgr.load_restore_payload(name)
    assert exc.value.status_code == 400


def test_restore_keeps_pre_restore_copy_of_live_files(tmp_path: Path):
    mgr = _manager(tmp_path)
    _db_with_row(mgr.db_path, 1)
    created = mgr.create_backup()
    _db_with_row(mgr.db_path, 2)
    mgr.env_path.write_text("X=live\n", encoding="utf-8")

    applied = mgr.restore_backup(created["file_name"])

    snapshot = Path(applied["pre_restore_snapshot"])
    assert snapshot.is_dir()
    assert sqlite3.connect(snapshot / "adminpanel.db").execute("SELECT x FROM t").fetchall() == [(2,)]
    assert (snapshot / ".env").read_text(encoding="utf-8") == "X=live\n"
    assert sqlite3.connect(mgr.db_path).execute("SELECT x FROM t").fetchall() == [(1,)]
    assert (snapshot.stat().st_mode & 0o777) == 0o700
    assert ((snapshot / ".env").stat().st_mode & 0o777) == 0o600


def test_restore_keeps_only_recent_pre_restore_copies(tmp_path: Path):
    mgr = _manager(tmp_path)
    created = mgr.create_backup()
    for _ in range(BackupManager.PRE_RESTORE_KEEP + 2):
        mgr.restore_backup(created["file_name"])
    snapshots = [p for p in (tmp_path / "backups" / BackupManager.PRE_RESTORE_DIR).iterdir() if p.is_dir()]
    assert len(snapshots) == BackupManager.PRE_RESTORE_KEEP


def test_restored_files_are_owner_only_and_old_wal_is_dropped(tmp_path: Path):
    mgr = _manager(tmp_path)
    _db_with_row(mgr.db_path, 1)
    created = mgr.create_backup()
    Path(f"{mgr.db_path}-wal").write_bytes(b"stale wal of the replaced database")

    mgr.restore_backup(created["file_name"])

    assert not Path(f"{mgr.db_path}-wal").exists()
    assert (mgr.db_path.stat().st_mode & 0o777) == 0o600
    assert (mgr.env_path.stat().st_mode & 0o777) == 0o600
    assert sqlite3.connect(mgr.db_path).execute("SELECT x FROM t").fetchall() == [(1,)]


def test_restore_rolls_back_replaced_files_when_a_later_write_fails(tmp_path: Path, monkeypatch):
    import os

    import pytest

    mgr = _manager(tmp_path)
    _db_with_row(mgr.db_path, 1)
    created = mgr.create_backup()
    _db_with_row(mgr.db_path, 2)
    mgr.env_path.write_text("X=live\n", encoding="utf-8")
    real_replace = os.replace

    def failing_replace(src, dst):
        if Path(dst) == mgr.env_path:
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr("app.services.backup_manager.os.replace", failing_replace)

    with pytest.raises(OSError):
        mgr.restore_backup(created["file_name"])

    assert sqlite3.connect(mgr.db_path).execute("SELECT x FROM t").fetchall() == [(2,)]
    assert mgr.env_path.read_text(encoding="utf-8") == "X=live\n"
    assert not list(mgr.env_path.parent.glob(".*.tmp"))


def test_restore_rejects_archive_db_failing_integrity_check(tmp_path: Path):
    import pytest
    from fastapi import HTTPException

    mgr = _manager(tmp_path)
    source = tmp_path / "source.db"
    conn = sqlite3.connect(source)
    conn.execute("PRAGMA page_size=1024")
    conn.execute("CREATE TABLE big(x TEXT)")
    conn.execute("CREATE INDEX ix ON big(x)")
    conn.executemany("INSERT INTO big VALUES (?)", [(f"v{i:05d}" * 20,) for i in range(300)])
    conn.commit()
    conn.close()
    data = bytearray(source.read_bytes())
    offset = (len(data) // 1024 - 1) * 1024 + 600
    data[offset : offset + 50] = b"Z" * 50
    name = _archive_with_db(tmp_path, bytes(data))

    with pytest.raises(HTTPException) as exc:
        mgr.load_restore_payload(name)
    assert exc.value.status_code == 400
