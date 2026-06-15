"""Tests for controller system update service."""

from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "backend" / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / "backend" / ".venv" / "bin" / "pip").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    return tmp_path


@patch("app.services.system_update.schedule_controller_restart")
@patch("app.services.system_update.build_frontend")
@patch("app.services.system_update.install_frontend_requirements")
@patch("app.services.system_update.install_backend_requirements")
@patch("app.services.system_update.git_pull")
def test_apply_controller_update_success(
    mock_pull,
    mock_pip,
    mock_npm,
    mock_build,
    mock_restart,
    tmp_path: Path,
):
    from app.services.system_update import apply_controller_update

    repo = _make_repo(tmp_path)
    mock_pull.return_value = {"success": True, "output": "Fast-forward", "error": None}
    mock_pip.return_value = {"skipped": False, "success": True, "output": "ok"}
    mock_npm.return_value = {"skipped": False, "success": True, "output": "ok"}
    mock_build.return_value = {"skipped": False, "success": True, "output": "built"}

    progress_calls: list[tuple[int, str]] = []

    def _progress(percent: int, stage: str) -> None:
        progress_calls.append((percent, stage))

    result = apply_controller_update(repo_root=repo, progress=_progress)

    assert result["success"] is True
    assert result["restarting"] is True
    assert "перезапускается" in result["message"]
    mock_restart.assert_called_once_with(repo)
    assert progress_calls[0][0] == 10
    assert progress_calls[-1][0] == 100


@patch("app.services.system_update.schedule_controller_restart")
@patch("app.services.system_update.build_frontend")
@patch("app.services.system_update.install_frontend_requirements")
@patch("app.services.system_update.install_backend_requirements")
@patch("app.services.system_update.git_pull")
def test_apply_controller_update_stops_on_npm_build_failure(
    mock_pull,
    mock_pip,
    mock_npm,
    mock_build,
    mock_restart,
    tmp_path: Path,
):
    from app.services.system_update import apply_controller_update

    repo = _make_repo(tmp_path)
    mock_pull.return_value = {"success": True, "output": "ok", "error": None}
    mock_pip.return_value = {"skipped": False, "success": True, "output": ""}
    mock_npm.return_value = {"skipped": False, "success": True, "output": ""}
    mock_build.return_value = {"skipped": False, "success": False, "output": "", "error": "build failed"}

    result = apply_controller_update(repo_root=repo)

    assert result["success"] is False
    assert "build failed" in result["errors"][0]
    mock_restart.assert_not_called()


@patch("app.services.system_update.subprocess.run")
def test_restart_controller_prefers_systemd(mock_run, tmp_path: Path):
    from app.services.system_update import restart_controller

    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),  # systemctl cat
        MagicMock(returncode=0, stdout="", stderr=""),  # systemctl restart
    ]

    result = restart_controller(tmp_path)

    assert result["success"] is True
    assert result["method"] == "systemd"
    assert mock_run.call_args_list[1].args[0] == ["systemctl", "restart", "adminpanelaz"]


def test_ensure_backend_data_dirs(tmp_path: Path):
    from app.services.system_update import ensure_backend_data_dirs

    ensure_backend_data_dirs(tmp_path)
    assert (tmp_path / "backend" / "data" / "cidr" / "list").is_dir()
    assert (tmp_path / "backend" / "data" / "cidr" / "staging").is_dir()
