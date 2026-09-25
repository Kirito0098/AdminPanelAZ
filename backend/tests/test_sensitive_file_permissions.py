import stat
from pathlib import Path

from app.services.security_bootstrap import restrict_sensitive_file_permissions


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_restricts_world_readable_secrets_to_owner_only(tmp_path: Path):
    env_file = tmp_path / ".env"
    db_file = tmp_path / "adminpanel.db"
    for path in (env_file, db_file):
        path.write_text("x", encoding="utf-8")
        path.chmod(0o644)

    restrict_sensitive_file_permissions([env_file, db_file])

    assert _mode(env_file) == 0o600
    assert _mode(db_file) == 0o600


def test_restricts_sqlite_sidecar_files(tmp_path: Path):
    db_file = tmp_path / "adminpanel.db"
    wal_file = tmp_path / "adminpanel.db-wal"
    for path in (db_file, wal_file):
        path.write_text("x", encoding="utf-8")
        path.chmod(0o644)

    restrict_sensitive_file_permissions([db_file])

    assert _mode(wal_file) == 0o600


def test_skips_missing_files(tmp_path: Path):
    restrict_sensitive_file_permissions([tmp_path / "missing.env"])
