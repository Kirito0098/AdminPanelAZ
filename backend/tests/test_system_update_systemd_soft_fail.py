"""Controller update soft-fails systemd refresh and still schedules restart."""

from pathlib import Path
from unittest.mock import MagicMock

from app.services import system_update


def test_apply_controller_update_continues_when_systemd_refresh_fails(tmp_path: Path, monkeypatch):
    (tmp_path / "backend" / "data").mkdir(parents=True)
    (tmp_path / "frontend").mkdir(parents=True)
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(system_update, "resolve_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        system_update,
        "git_pull",
        lambda _root: {"success": True, "output": "Already up to date.", "error": None},
    )
    monkeypatch.setattr(
        system_update,
        "install_backend_requirements",
        lambda _root: {"success": True, "skipped": True, "output": "skip", "error": None},
    )
    monkeypatch.setattr(
        system_update,
        "install_frontend_requirements",
        lambda _root: {"success": True, "skipped": True, "output": "skip", "error": None},
    )
    monkeypatch.setattr(
        system_update,
        "build_frontend",
        lambda _root: {"success": True, "skipped": False, "output": "built", "error": None},
    )
    monkeypatch.setattr(
        system_update,
        "refresh_installed_systemd_units",
        lambda _root, panel=True, node=True: {
            "success": False,
            "skipped": False,
            "output": "Run as root",
            "error": "Run as root",
        },
    )
    restart = MagicMock()
    monkeypatch.setattr(system_update, "schedule_controller_restart", restart)

    result = system_update.apply_controller_update(repo_root=tmp_path)

    assert result["success"] is True
    assert result["restarting"] is True
    assert result["errors"] == []
    assert "Предупреждение" in result["output"]
    assert "Run as root" in result["output"]
    restart.assert_called_once_with(tmp_path)
