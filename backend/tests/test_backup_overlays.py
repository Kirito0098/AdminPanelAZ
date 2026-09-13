from pathlib import Path
from unittest.mock import MagicMock

from app.services.backup_overlays import apply_backup_overlays
from app.services.backup_manager import BackupManager


def test_local_mode_writes_routing_lists(tmp_path: Path):
    root = tmp_path / "az" / "config"
    payload = {
        "configs": {"include-hosts.txt": "example.com\n", "skip-me.txt": "nope"},
        "_files": {},
    }
    apply_backup_overlays(payload, mode="local", config_root=root)
    assert (root / "include-hosts.txt").read_text(encoding="utf-8") == "example.com\n"
    assert not (root / "skip-me.txt").exists()
    assert set(p.name for p in root.iterdir()) <= set(BackupManager.CONFIG_FILES)


def test_local_mode_uses_antizapret_path_env_when_config_root_omitted(tmp_path, monkeypatch):
    az_root = tmp_path / "az-root"
    monkeypatch.setenv("ANTIZAPRET_PATH", str(az_root))
    apply_backup_overlays(
        {"configs": {"include-hosts.txt": "example.com\n"}, "_files": {}},
        mode="local",
        config_root=None,
    )
    assert (az_root / "config" / "include-hosts.txt").read_text(encoding="utf-8") == "example.com\n"


def test_local_mode_imports_awg2(tmp_path, monkeypatch):
    service = MagicMock()
    service.import_narrow_backup.return_value = None
    service.apply_runtime.return_value = {"success": True}
    monkeypatch.setattr("app.services.backup_overlays.Awg2Service", lambda: service)
    apply_backup_overlays(
        {"configs": {}, "_files": {"awg2": b"overlay"}},
        mode="local",
        config_root=tmp_path / "config",
    )
    service.import_narrow_backup.assert_called_once_with(b"overlay")
    service.apply_runtime.assert_called_once()


def test_local_mode_awg2_failure_does_not_raise(tmp_path, monkeypatch):
    service = MagicMock()
    service.import_narrow_backup.side_effect = RuntimeError("boom")
    monkeypatch.setattr("app.services.backup_overlays.Awg2Service", lambda: service)
    apply_backup_overlays(
        {"configs": {"include-hosts.txt": "x\n"}, "_files": {"awg2": b"overlay"}},
        mode="local",
        config_root=tmp_path / "config",
    )
    assert (tmp_path / "config" / "include-hosts.txt").is_file()


def test_local_mode_logs_runtime_warning_when_apply_fails(tmp_path, monkeypatch, caplog):
    service = MagicMock()
    service.import_narrow_backup.return_value = None
    service.apply_runtime.return_value = {"success": False, "errors": ["awg-quick failed"]}
    monkeypatch.setattr("app.services.backup_overlays.Awg2Service", lambda: service)
    with caplog.at_level("WARNING"):
        apply_backup_overlays(
            {"configs": {}, "_files": {"awg2": b"overlay"}},
            mode="local",
            config_root=tmp_path / "config",
        )
    assert "runtime apply after panel restore failed" in caplog.text
    assert "awg-quick failed" in caplog.text


def test_adapter_mode_writes_lists_then_awg2_then_ha(monkeypatch):
    order: list[str] = []
    adapter = MagicMock()
    adapter.write_config_file.side_effect = lambda name, content: order.append(f"list:{name}")
    adapter.restore_awg2_backup.side_effect = lambda data: order.append("awg2") or {"success": True}
    monkeypatch.setattr("app.services.backup_overlays.get_active_adapter", lambda _db: adapter)
    monkeypatch.setattr(
        "app.routers.awg2._ha_sync_awg2_from_active",
        lambda _db: order.append("ha") or {"attempted": True, "errors": []},
    )
    apply_backup_overlays(
        {"configs": {"include-hosts.txt": "x"}, "_files": {"awg2": b"ov"}},
        mode="adapter",
        db=MagicMock(),
    )
    assert order == ["list:include-hosts.txt", "awg2", "ha"]


def test_adapter_mode_requires_db():
    import pytest

    with pytest.raises(ValueError):
        apply_backup_overlays({"configs": {}, "_files": {}}, mode="adapter")
