"""Agent update refuses to restart into a node agent that could not start (mTLS on, certificates missing)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import node_update, systemd_refresh

ALL_CERTS = ("agent.crt", "agent.key", "ca.crt")


@pytest.fixture
def node_env(tmp_path: Path, monkeypatch):
    env_file = tmp_path / "node_agent.env"
    monkeypatch.setenv("NODE_AGENT_ENV_FILE", str(env_file))

    def write(enabled: str, *present: str) -> Path:
        env_file.write_text(
            f"NODE_AGENT_MTLS_ENABLED={enabled}\n"
            f"NODE_AGENT_MTLS_SERVER_CERT={tmp_path / 'agent.crt'}\n"
            f"NODE_AGENT_MTLS_SERVER_KEY={tmp_path / 'agent.key'}\n"
            f"NODE_AGENT_MTLS_CA_CERT={tmp_path / 'ca.crt'}\n",
            encoding="utf-8",
        )
        for name in present:
            (tmp_path / name).write_text(name, encoding="utf-8")
        return tmp_path

    return write


@pytest.fixture
def update_steps(monkeypatch):
    steps: list[str] = []
    monkeypatch.setattr(node_update, "git_pull", lambda _root: steps.append("pull") or {"success": True})
    monkeypatch.setattr(node_update, "_pip_install", lambda _root: steps.append("pip") or {"skipped": True})
    monkeypatch.setattr(systemd_refresh, "refresh_installed_systemd_units", lambda *_a, **_k: {"success": True})
    monkeypatch.setattr(node_update, "schedule_agent_restart", lambda _root: steps.append("restart"))
    return steps


def test_update_refused_when_mtls_on_and_certificates_missing(node_env, update_steps):
    root = node_env("true", "ca.crt")

    result = node_update.apply_node_update(agent_version="1.12.0", repo_root=root)

    assert result["success"] is False
    assert result["restarting"] is False
    assert update_steps == []
    error = result["errors"][0]
    assert error.startswith("Обновление node agent отменено: mTLS включён")
    assert str(root / "agent.crt") in error
    assert str(root / "agent.key") in error
    assert str(root / "ca.crt") not in error


@pytest.mark.parametrize(
    "enabled, present",
    [("true", ALL_CERTS), ("YES", ALL_CERTS), ("false", ())],
)
def test_update_proceeds_when_restart_is_safe(node_env, update_steps, enabled, present):
    root = node_env(enabled, *present)

    result = node_update.apply_node_update(agent_version="1.12.0", repo_root=root)

    assert result["success"] is True
    assert update_steps == ["pull", "pip", "restart"]


def test_agent_returns_the_refusal_to_the_panel(node_env, update_steps, monkeypatch):
    root = node_env("1")
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "n" * 32)
    os.environ.pop("NODE_AGENT_ALLOWED_IPS", None)
    import node_agent.main as agent_main

    monkeypatch.setattr(agent_main, "resolve_repo_root", lambda: root)

    response = TestClient(agent_main.app).post(
        "/system/update", json={}, headers={"X-Node-Key": agent_main.NODE_AGENT_API_KEY}
    )

    assert response.status_code == 500
    assert "сертификатов нет" in response.json()["detail"]
    assert update_steps == []
