"""Tests for node agent POST /system/provision-mtls."""

from __future__ import annotations

import importlib
import stat
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services import node_mtls_certs as certs_svc
from app.services.node_agent_provision import (
    persist_mtls_files,
    persist_node_agent_env_mtls,
    provision_mtls,
    validate_mtls_bundle,
)


@pytest.fixture()
def mtls_bundle(tmp_path, monkeypatch):
    mtls_dir = tmp_path / "panel_mtls"
    settings = Settings(node_agent_mtls_dir=mtls_dir)
    monkeypatch.setattr("app.services.node_mtls_certs.get_settings", lambda: settings)
    certs_svc.ensure_panel_mtls_materials()
    certs_svc.generate_agent_cert_for_node(1, "test-node")
    return certs_svc.read_agent_bundle_for_node(1)


@pytest.fixture()
def node_paths(tmp_path, monkeypatch):
    mtls_dir = tmp_path / "mtls"
    env_file = tmp_path / "node_agent.env"
    env_file.write_text("NODE_AGENT_API_KEY=old\nNODE_AGENT_PORT=9100\n", encoding="utf-8")
    monkeypatch.setenv("NODE_AGENT_MTLS_CA_CERT", str(mtls_dir / "ca.crt"))
    monkeypatch.setenv("NODE_AGENT_MTLS_SERVER_CERT", str(mtls_dir / "agent.crt"))
    monkeypatch.setenv("NODE_AGENT_MTLS_SERVER_KEY", str(mtls_dir / "agent.key"))
    monkeypatch.setenv("NODE_AGENT_ENV_FILE", str(env_file))
    return {"mtls_dir": mtls_dir, "env_file": env_file}


def test_validate_mtls_bundle_rejects_short_pem():
    with pytest.raises(ValueError, match="слишком короткий"):
        validate_mtls_bundle("x", "y", "z")


def test_validate_mtls_bundle_rejects_missing_markers():
    short = "A" * 80
    with pytest.raises(ValueError, match="BEGIN CERTIFICATE"):
        validate_mtls_bundle(short, short, short)


def test_persist_mtls_files_writes_with_permissions(mtls_bundle, node_paths):
    paths = persist_mtls_files(
        mtls_bundle.ca_pem,
        mtls_bundle.agent_cert_pem,
        mtls_bundle.agent_key_pem,
    )

    mtls_dir = node_paths["mtls_dir"]
    assert paths["ca_cert"] == str(mtls_dir / "ca.crt")
    assert (mtls_dir / "ca.crt").is_file()
    assert (mtls_dir / "agent.crt").is_file()
    assert (mtls_dir / "agent.key").is_file()
    assert stat.S_IMODE(mtls_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((mtls_dir / "agent.key").stat().st_mode) == 0o600
    assert stat.S_IMODE((mtls_dir / "agent.crt").stat().st_mode) == 0o644


def test_persist_node_agent_env_mtls_updates_flags(node_paths):
    paths = {
        "ca_cert": str(node_paths["mtls_dir"] / "ca.crt"),
        "server_cert": str(node_paths["mtls_dir"] / "agent.crt"),
        "server_key": str(node_paths["mtls_dir"] / "agent.key"),
    }
    persist_node_agent_env_mtls(paths)

    content = node_paths["env_file"].read_text(encoding="utf-8")
    assert "NODE_AGENT_MTLS_ENABLED=true" in content
    assert f"NODE_AGENT_MTLS_CA_CERT={paths['ca_cert']}" in content
    assert f"NODE_AGENT_MTLS_SERVER_CERT={paths['server_cert']}" in content
    assert f"NODE_AGENT_MTLS_SERVER_KEY={paths['server_key']}" in content
    assert "NODE_AGENT_API_KEY=old" in content


def test_persist_node_agent_env_mtls_writes_backend_and_legacy_env(tmp_path, monkeypatch):
    repo = tmp_path / "AdminPanelAZ"
    backend_env = repo / "backend" / "node_agent.env"
    backend_env.parent.mkdir(parents=True)
    backend_env.write_text("NODE_AGENT_API_KEY=old\n", encoding="utf-8")
    (repo / ".git").mkdir()
    legacy_env = tmp_path / "etc" / "adminpanelaz" / "node_agent.env"
    legacy_env.parent.mkdir(parents=True)

    monkeypatch.setenv("NODE_AGENT_ENV_FILE", str(legacy_env))
    monkeypatch.setenv("NODE_AGENT_MTLS_CA_CERT", str(tmp_path / "mtls" / "ca.crt"))
    monkeypatch.setenv("NODE_AGENT_MTLS_SERVER_CERT", str(tmp_path / "mtls" / "agent.crt"))
    monkeypatch.setenv("NODE_AGENT_MTLS_SERVER_KEY", str(tmp_path / "mtls" / "agent.key"))

    paths = {
        "ca_cert": str(tmp_path / "mtls" / "ca.crt"),
        "server_cert": str(tmp_path / "mtls" / "agent.crt"),
        "server_key": str(tmp_path / "mtls" / "agent.key"),
    }
    with patch("app.services.node_agent_env.resolve_repo_root", return_value=repo):
        persist_node_agent_env_mtls(paths)

    for env_file in (backend_env, legacy_env):
        content = env_file.read_text(encoding="utf-8")
        assert "NODE_AGENT_MTLS_ENABLED=true" in content
        assert f"NODE_AGENT_MTLS_CA_CERT={paths['ca_cert']}" in content


@patch("app.services.node_agent_provision.schedule_agent_restart")
def test_provision_mtls_with_restart(mock_restart, mtls_bundle, node_paths, tmp_path):
    (tmp_path / ".git").mkdir()

    result = provision_mtls(
        ca_pem=mtls_bundle.ca_pem,
        agent_cert_pem=mtls_bundle.agent_cert_pem,
        agent_key_pem=mtls_bundle.agent_key_pem,
        restart=True,
        repo_root=tmp_path,
    )

    assert result["success"] is True
    assert result["mtls_enabled"] is True
    assert result["restart"]["method"] == "scheduled"
    assert (node_paths["mtls_dir"] / "agent.crt").is_file()
    assert "NODE_AGENT_MTLS_ENABLED=true" in node_paths["env_file"].read_text(encoding="utf-8")
    mock_restart.assert_called_once_with(tmp_path)


@patch("app.services.node_agent_provision.schedule_agent_restart")
def test_provision_mtls_skips_restart_when_disabled(mock_restart, mtls_bundle, node_paths, tmp_path):
    result = provision_mtls(
        ca_pem=mtls_bundle.ca_pem,
        agent_cert_pem=mtls_bundle.agent_cert_pem,
        agent_key_pem=mtls_bundle.agent_key_pem,
        restart=False,
        repo_root=tmp_path,
    )

    assert result["success"] is True
    assert result["restart"] is None
    mock_restart.assert_not_called()


def _node_agent_test_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    api_key = "k" * 32
    mtls_dir = tmp_path / "agent_mtls"
    env_file = tmp_path / "node_agent.env"
    env_file.write_text(f"NODE_AGENT_API_KEY={api_key}\n", encoding="utf-8")

    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", api_key)
    monkeypatch.setenv("NODE_AGENT_ENV_FILE", str(env_file))
    monkeypatch.setenv("NODE_AGENT_MTLS_CA_CERT", str(mtls_dir / "ca.crt"))
    monkeypatch.setenv("NODE_AGENT_MTLS_SERVER_CERT", str(mtls_dir / "agent.crt"))
    monkeypatch.setenv("NODE_AGENT_MTLS_SERVER_KEY", str(mtls_dir / "agent.key"))

    import node_agent.main as main_mod

    importlib.reload(main_mod)
    return TestClient(main_mod.app), api_key


@patch("app.services.node_agent_provision.schedule_agent_restart")
def test_provision_mtls_endpoint_writes_files(
    mock_restart,
    mtls_bundle,
    tmp_path,
    monkeypatch,
):
    (tmp_path / ".git").mkdir()
    client, api_key = _node_agent_test_client(tmp_path, monkeypatch)

    response = client.post(
        "/system/provision-mtls",
        headers={"X-Node-Key": api_key},
        json={
            "ca_pem": mtls_bundle.ca_pem,
            "agent_cert_pem": mtls_bundle.agent_cert_pem,
            "agent_key_pem": mtls_bundle.agent_key_pem,
            "restart": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["mtls_enabled"] is True

    mtls_dir = tmp_path / "agent_mtls"
    assert (mtls_dir / "ca.crt").is_file()
    assert (mtls_dir / "agent.crt").is_file()
    assert (mtls_dir / "agent.key").is_file()
    env_text = (tmp_path / "node_agent.env").read_text(encoding="utf-8")
    assert "NODE_AGENT_MTLS_ENABLED=true" in env_text


def test_provision_mtls_endpoint_requires_api_key(mtls_bundle, tmp_path, monkeypatch):
    client, _ = _node_agent_test_client(tmp_path, monkeypatch)

    response = client.post(
        "/system/provision-mtls",
        json={
            "ca_pem": mtls_bundle.ca_pem,
            "agent_cert_pem": mtls_bundle.agent_cert_pem,
            "agent_key_pem": mtls_bundle.agent_key_pem,
        },
    )

    assert response.status_code == 422 or response.status_code == 401


def test_provision_mtls_endpoint_rejects_invalid_pem(tmp_path, monkeypatch):
    client, api_key = _node_agent_test_client(tmp_path, monkeypatch)
    bad = "not-a-pem" * 10

    response = client.post(
        "/system/provision-mtls",
        headers={"X-Node-Key": api_key},
        json={
            "ca_pem": bad,
            "agent_cert_pem": bad,
            "agent_key_pem": bad,
        },
    )

    assert response.status_code == 400
