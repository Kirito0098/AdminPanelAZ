from unittest.mock import MagicMock

from app.routers import backups as backups_mod

def test_restore_awg2_overlay_uses_adapter_then_ha_sync(monkeypatch):
    adapter = MagicMock()
    adapter.restore_awg2_backup.return_value = {"success": True}
    ha = MagicMock(return_value={"attempted": True, "errors": []})
    monkeypatch.setattr(backups_mod, "get_active_adapter", lambda _db: adapter)
    monkeypatch.setattr("app.routers.awg2._ha_sync_awg2_from_active", ha)

    backups_mod._restore_awg2_overlay(MagicMock(), {"_files": {"awg2": b"overlay"}})

    adapter.restore_awg2_backup.assert_called_once_with(b"overlay")
    ha.assert_called_once()


def test_restore_awg2_overlay_skips_when_missing():
    backups_mod._restore_awg2_overlay(MagicMock(), {"_files": {}})


def test_restore_panel_disposes_engines_before_applying_files(monkeypatch):
    order: list[str] = []

    class FakeManager:
        def load_restore_payload(self, file_name: str) -> dict:
            order.append("load")
            return {"restored": ["db"], "file_name": file_name, "configs": {"include-hosts.txt": "x"}}

        def apply_restore_payload(self, payload: dict) -> dict:
            order.append("apply")
            return payload

    monkeypatch.setattr(
        backups_mod,
        "_write_restored_configs",
        lambda _db, configs: order.append(f"configs:{len(configs)}"),
    )
    monkeypatch.setattr(
        backups_mod,
        "_restore_awg2_overlay",
        lambda _db, payload: order.append(f"awg2:{int(bool((payload.get('_files') or {}).get('awg2')))}"),
    )
    monkeypatch.setattr(backups_mod, "_dispose_db_engines", lambda: order.append("dispose"))
    monkeypatch.setattr(
        backups_mod,
        "_schedule_panel_restart_after_restore",
        lambda: order.append("restart"),
    )

    result = backups_mod._restore_panel_and_restart(FakeManager(), "panel.tar.gz", MagicMock())

    assert result["file_name"] == "panel.tar.gz"
    assert order == ["load", "configs:1", "awg2:0", "dispose", "apply", "restart"]
