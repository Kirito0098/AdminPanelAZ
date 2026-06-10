"""Tests for node agent env file path resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_resolve_node_agent_env_file_prefers_repo_backend(tmp_path):
    from app.services.node_agent_env import resolve_node_agent_env_file

    repo = tmp_path / "AdminPanelAZ"
    (repo / "backend").mkdir(parents=True)
    (repo / ".git").mkdir()

    with patch("app.services.node_agent_env.resolve_repo_root", return_value=repo):
        assert resolve_node_agent_env_file() == repo / "backend" / "node_agent.env"


def test_resolve_node_agent_env_file_honors_override(tmp_path, monkeypatch):
    from app.services.node_agent_env import resolve_node_agent_env_file

    override = tmp_path / "custom.env"
    monkeypatch.setenv("NODE_AGENT_ENV_FILE", str(override))

    with patch("app.services.node_agent_env.resolve_repo_root", return_value=None):
        assert resolve_node_agent_env_file() == override


def test_node_agent_env_targets_includes_backend_and_legacy(tmp_path, monkeypatch):
    from app.services.node_agent_env import node_agent_env_targets

    repo = tmp_path / "AdminPanelAZ"
    backend_env = repo / "backend" / "node_agent.env"
    backend_env.parent.mkdir(parents=True)
    backend_env.write_text("NODE_AGENT_API_KEY=test\n", encoding="utf-8")
    (repo / ".git").mkdir()
    legacy_env = tmp_path / "etc" / "adminpanelaz" / "node_agent.env"
    legacy_env.parent.mkdir(parents=True)
    legacy_env.write_text("NODE_AGENT_API_KEY=legacy\n", encoding="utf-8")

    monkeypatch.setenv("NODE_AGENT_ENV_FILE", str(legacy_env))

    with patch("app.services.node_agent_env.resolve_repo_root", return_value=repo):
        targets = node_agent_env_targets()

    assert legacy_env in targets
    assert backend_env in targets
