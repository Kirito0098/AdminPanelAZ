"""Tests for node update service."""

from pathlib import Path
from unittest.mock import MagicMock, patch


def test_resolve_repo_root_finds_git(tmp_path: Path):
    from app.services.node_update import resolve_repo_root

    (tmp_path / ".git").mkdir()
    assert resolve_repo_root(tmp_path) == tmp_path


def test_check_git_updates_no_repo(tmp_path: Path):
    from app.services.node_update import check_git_updates

    result = check_git_updates(tmp_path / "missing")
    assert result["updates_available"] is False
    assert "error" in result


@patch("app.services.node_update._git_run")
def test_check_git_updates_up_to_date(mock_git_run, tmp_path: Path):
    from app.services.node_update import check_git_updates

    (tmp_path / ".git").mkdir()
    mock_git_run.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),
        MagicMock(returncode=0, stdout="abc123def456\n", stderr=""),
        MagicMock(returncode=0, stdout="abc123def456\n", stderr=""),
    ]

    result = check_git_updates(tmp_path)
    assert result["updates_available"] is False
    assert result["commits_behind"] == 0
    assert result["local_hash"] == "abc123def456"


@patch("app.services.node_update.schedule_agent_restart")
@patch("app.services.node_update.git_pull")
def test_apply_node_update(mock_pull, mock_restart, tmp_path: Path):
    from app.services.node_update import apply_node_update

    (tmp_path / ".git").mkdir()
    mock_pull.return_value = {"success": True, "output": "Already up to date.", "error": None}

    result = apply_node_update(
        agent_version="1.0.0",
        repo_root=tmp_path,
    )

    assert result["success"] is True
    assert result["restarting"] is True
    mock_pull.assert_called_once()
    mock_restart.assert_called_once_with(tmp_path)


@patch("app.services.node_update.subprocess.run")
def test_restart_node_agent_prefers_systemd(mock_run, tmp_path: Path):
    from app.services.node_update import restart_node_agent

    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),  # systemctl cat
        MagicMock(returncode=0, stdout="", stderr=""),  # systemctl restart
    ]

    result = restart_node_agent(tmp_path)

    assert result["success"] is True
    assert result["method"] == "systemd"
    assert mock_run.call_args_list[1].args[0] == ["systemctl", "restart", "adminpanelaz-node"]


@patch("app.services.node_update.subprocess.run")
def test_restart_node_agent_falls_back_to_script(mock_run, tmp_path: Path):
    from app.services.node_update import restart_node_agent

    script = tmp_path / "start_node_agent.sh"
    script.write_text("#!/bin/bash\n", encoding="utf-8")
    script.chmod(0o755)

    mock_run.side_effect = [
        MagicMock(returncode=1, stdout="", stderr=""),  # systemctl cat — unit missing
        MagicMock(returncode=0, stdout="ok", stderr=""),
    ]

    result = restart_node_agent(tmp_path)

    assert result["success"] is True
    assert result["method"] == "script"
