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
def test_apply_node_update_agent_scope(mock_pull, mock_restart, tmp_path: Path):
    from app.services.node_update import apply_node_update

    (tmp_path / ".git").mkdir()
    service = MagicMock()
    service.get_antizapret_version.return_value = "v1.0"
    mock_pull.return_value = {"success": True, "output": "Already up to date.", "error": None}

    result = apply_node_update(
        antizapret_path=tmp_path,
        service=service,
        scope="agent",
        run_doall=False,
        agent_version="1.0.0",
        repo_root=tmp_path,
    )

    assert result["success"] is True
    assert result["restarting"] is True
    mock_pull.assert_called_once()
    mock_restart.assert_called_once_with(tmp_path)


@patch("app.services.node_update.git_pull")
def test_apply_node_update_antizapret_with_doall(mock_pull, tmp_path: Path):
    from app.services.node_update import apply_node_update

    az_path = tmp_path / "antizapret"
    az_path.mkdir()
    (az_path / ".git").mkdir()

    service = MagicMock()
    service.get_antizapret_version.side_effect = ["v1.0", "v1.1"]
    service.apply_config_changes.return_value = "doall ok"
    mock_pull.return_value = {"success": True, "output": "Updated.", "error": None}

    result = apply_node_update(
        antizapret_path=az_path,
        service=service,
        scope="antizapret",
        run_doall=True,
        repo_root=None,
    )

    assert result["success"] is True
    assert result["after"]["antizapret_version"] == "v1.1"
    service.apply_config_changes.assert_called_once()
