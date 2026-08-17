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
