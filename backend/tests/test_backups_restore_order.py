from unittest.mock import MagicMock

import sqlite3

from app.routers import backups as backups_mod


def test_backup_entry_schema_accepts_restore_detail():
    from app.schemas import BackupEntry

    entry = BackupEntry(
        file_name="adminpanelaz_x.tar.gz",
        size_bytes=10,
        created_at="2026-09-12T00:00:00Z",
        components=["db"],
        summary="db",
        restore_message="Восстановление выполнено. Панель будет перезапущена через несколько секунд.",
        restore_detail={"restart_scheduled": True, "hint": "Push full"},
    )
    assert entry.restore_detail["hint"] == "Push full"


def test_restore_response_includes_apply_hint_for_restored_configs():
    response = backups_mod._restore_response({"restored": ["db", "configs"], "file_name": "panel.tar.gz"})
    assert response.detail["restart_scheduled"] is True
    assert "Примен" in response.detail["hint"]


def test_restore_response_includes_push_full_hint_for_configs():
    response = backups_mod._restore_response(
        {"restored": ["db", "configs"], "file_name": "panel.tar.gz"}
    )
    assert "Push full" in response.detail["hint"]
    assert "Примен" in response.detail["hint"]


def test_restore_response_includes_push_full_hint_for_awg2_only():
    response = backups_mod._restore_response(
        {"restored": ["db", "awg2"], "file_name": "panel.tar.gz"}
    )
    assert "Push full" in response.detail["hint"]
    assert "Примен" not in response.detail.get("hint", "")


def test_restore_panel_disposes_engines_before_applying_files(monkeypatch, tmp_path):
    order: list[str] = []
    db = tmp_path / "adminpanel.db"
    env = tmp_path / ".env"
    sqlite3.connect(db).close()
    env.write_text("", encoding="utf-8")

    class FakeManager:
        db_path = db
        env_path = env

        def load_restore_payload(self, file_name: str) -> dict:
            order.append("load")
            return {
                "restored": ["db"],
                "file_name": file_name,
                "configs": {"include-hosts.txt": "x"},
                "_files": {"awg2": b"ov"},
            }

        def apply_restore_payload(self, payload: dict) -> dict:
            order.append("apply")
            return payload

    monkeypatch.setattr(
        backups_mod,
        "apply_backup_overlays",
        lambda payload, mode, db=None, config_root=None: order.append(
            f"overlays:{mode}:{len(payload.get('configs') or {})}:{int(bool((payload.get('_files') or {}).get('awg2')))}"
        ),
    )
    monkeypatch.setattr(backups_mod, "_dispose_db_engines", lambda: order.append("dispose"))
    monkeypatch.setattr(
        backups_mod,
        "_schedule_panel_restart_after_restore",
        lambda: order.append("restart"),
    )

    result = backups_mod._restore_panel_and_restart(FakeManager(), "panel.tar.gz", MagicMock())
    assert result["file_name"] == "panel.tar.gz"
    assert result["portal_reprovision_needed"] is False
    assert order == ["load", "overlays:adapter:1:1", "dispose", "apply", "restart"]


def test_restore_backup_records_audit_after_db_replace(monkeypatch):
    order: list[str] = []

    monkeypatch.setattr(backups_mod, "_get_backup_manager", lambda: object())
    monkeypatch.setattr(
        backups_mod,
        "_restore_panel_and_restart",
        lambda manager, file_name, db: order.append("restore") or {
            "restored": ["db"],
            "file_name": file_name,
        },
    )
    monkeypatch.setattr(
        backups_mod,
        "_record_backup_restore_side_effects",
        lambda **kwargs: order.append(f"audit:{kwargs['details']}"),
    )

    response = backups_mod.restore_backup(
        MagicMock(file_name="panel.tar.gz"),
        MagicMock(),
        MagicMock(),
        MagicMock(id=1, username="admin"),
    )

    assert order == ["restore", "audit:panel.tar.gz"]
    assert response.message == backups_mod.RESTORE_RESTART_MESSAGE


def test_record_backup_restore_side_effects_uses_fresh_session(monkeypatch):
    """After dispose+replace, request-scoped db is stale — open SessionLocal."""
    fake_db = MagicMock()
    closed: list[bool] = []

    class FakeSessionLocal:
        def __call__(self):
            return fake_db

    fake_db.close = lambda: closed.append(True)

    calls: list[str] = []

    monkeypatch.setattr("app.database.SessionLocal", FakeSessionLocal())
    monkeypatch.setattr(backups_mod.settings, "audit_log_enabled", True)
    monkeypatch.setattr(
        backups_mod,
        "log_action",
        lambda db, **kwargs: calls.append(f"log:{kwargs['details']}") or None,
    )
    monkeypatch.setattr(
        backups_mod.admin_notify_service,
        "send_settings_change",
        lambda db, **kwargs: calls.append(f"notify:{kwargs['subject_name']}"),
    )
    monkeypatch.setattr(
        backups_mod.ip_restriction_service,
        "get_client_ip",
        lambda request: "127.0.0.1",
    )
    monkeypatch.setattr(
        backups_mod,
        "get_client_timezone_from_request",
        lambda request: "UTC",
    )

    backups_mod._record_backup_restore_side_effects(
        admin=MagicMock(id=7, username="ops"),
        request=MagicMock(),
        file_name="panel.tar.gz",
        details="upload:panel.tar.gz",
    )

    assert calls == ["log:upload:panel.tar.gz", "notify:panel.tar.gz"]
    assert closed == [True]
