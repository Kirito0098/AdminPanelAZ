from unittest.mock import MagicMock

from app.routers import backups as backups_mod


def test_restore_response_includes_apply_hint_for_restored_configs():
    response = backups_mod._restore_response({"restored": ["db", "configs"], "file_name": "panel.tar.gz"})
    assert response.detail["restart_scheduled"] is True
    assert "Примен" in response.detail["hint"]


def test_restore_panel_disposes_engines_before_applying_files(monkeypatch):
    order: list[str] = []

    class FakeManager:
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
    assert order == ["load", "overlays:adapter:1:1", "dispose", "apply", "restart"]
