from pathlib import Path
import sqlite3

from app.services.backup_manager import BackupManager
from app.services.client_portal import (
    PORTAL_RESTORE_HINT,
    sync_portal_domain_after_restore,
)
from app.routers import backups as backups_mod


def _seed_portal_db(db_path: Path, *, domain: str, token: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_settings ("
            "id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS client_portal_tokens ("
            "id INTEGER PRIMARY KEY, token TEXT UNIQUE, client_name TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            ("portal_domain", domain),
        )
        conn.execute(
            "INSERT OR REPLACE INTO client_portal_tokens (id, token, client_name) VALUES (1, ?, ?)",
            (token, "alice"),
        )
        conn.commit()
    finally:
        conn.close()


def test_sync_portal_domain_after_restore_writes_env(tmp_path: Path):
    db = tmp_path / "adminpanel.db"
    env = tmp_path / ".env"
    env.write_text("PORTAL_DOMAIN=stale.example.com\nOTHER=1\n", encoding="utf-8")
    _seed_portal_db(db, domain="portal.example.com", token="tok-1")

    meta = sync_portal_domain_after_restore(db_path=db, env_path=env)
    assert meta["portal_domain"] == "portal.example.com"
    assert meta["portal_reprovision_needed"] is True
    assert meta["portal_hint"] == PORTAL_RESTORE_HINT
    text = env.read_text(encoding="utf-8")
    assert "PORTAL_DOMAIN=portal.example.com\n" in text
    assert "OTHER=1" in text


def test_sync_portal_domain_skips_when_empty(tmp_path: Path):
    db = tmp_path / "adminpanel.db"
    env = tmp_path / ".env"
    env.write_text("PORTAL_DOMAIN=keep.example.com\n", encoding="utf-8")
    sqlite3.connect(db).close()
    meta = sync_portal_domain_after_restore(db_path=db, env_path=env)
    assert meta["portal_reprovision_needed"] is False
    assert meta["portal_domain"] is None
    assert env.read_text(encoding="utf-8") == "PORTAL_DOMAIN=keep.example.com\n"


def test_backup_roundtrip_restores_portal_rows_and_env(tmp_path: Path):
    db = tmp_path / "adminpanel.db"
    env = tmp_path / ".env"
    env.write_text("X=1\n", encoding="utf-8")
    _seed_portal_db(db, domain="portal.roundtrip.test", token="portal-tok-abc")

    mgr = BackupManager(
        app_root=tmp_path,
        backup_root=tmp_path / "backups",
        db_path=db,
        env_path=env,
    )
    created = mgr.create_backup()

    # Wipe live state
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM app_settings")
    conn.execute("DELETE FROM client_portal_tokens")
    conn.commit()
    conn.close()
    env.write_text("PORTAL_DOMAIN=wrong.example.com\n", encoding="utf-8")

    payload = mgr.load_restore_payload(created["file_name"])
    mgr.apply_restore_payload(payload)
    meta = sync_portal_domain_after_restore(db_path=db, env_path=env)

    assert meta["portal_reprovision_needed"] is True
    assert meta["portal_domain"] == "portal.roundtrip.test"
    assert "PORTAL_DOMAIN=portal.roundtrip.test\n" in env.read_text(encoding="utf-8")

    conn = sqlite3.connect(db)
    try:
        domain = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'portal_domain'"
        ).fetchone()[0]
        token = conn.execute(
            "SELECT token FROM client_portal_tokens WHERE client_name = 'alice'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert domain == "portal.roundtrip.test"
    assert token == "portal-tok-abc"


def test_restore_response_includes_portal_hint():
    response = backups_mod._restore_response(
        {
            "restored": ["db"],
            "file_name": "panel.tar.gz",
            "portal_reprovision_needed": True,
            "portal_domain": "portal.example.com",
            "portal_hint": PORTAL_RESTORE_HINT,
        }
    )
    assert response.detail["portal_reprovision_needed"] is True
    assert response.detail["portal_domain"] == "portal.example.com"
    assert "Подписка" in response.detail["hint"]
