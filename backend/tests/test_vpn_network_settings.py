"""API tests for GET /api/settings/vpn-network."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.env_file import EnvFileService
from app.services.feature_toggles import FeatureToggleService


@pytest.fixture()
def vpn_api_client(api_test_env, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "FEATURE_VPN_NETWORK_ENABLED=true",
                "BACKEND_HOST=127.0.0.1",
                "BACKEND_PORT=8000",
                "BEHIND_NGINX=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.routers.maintenance.get_feature_service",
        lambda: FeatureToggleService(env_file),
    )

    with patch("app.routers.maintenance.EnvFileService", return_value=EnvFileService(env_file)):
        from app.main import app

        yield TestClient(app), api_test_env


@pytest.fixture()
def vpn_disabled_api_client(api_test_env, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_VPN_NETWORK_ENABLED=false\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.routers.maintenance.get_feature_service",
        lambda: FeatureToggleService(env_file),
    )

    from app.main import app

    yield TestClient(app), api_test_env


def test_get_vpn_network_settings_requires_admin(vpn_api_client):
    client, env = vpn_api_client
    resp = client.get("/api/settings/vpn-network")
    assert resp.status_code == 401

    resp = client.get("/api/settings/vpn-network", headers=env["viewer_headers"])
    assert resp.status_code == 403


def test_get_vpn_network_settings_ok(vpn_api_client):
    client, env = vpn_api_client
    resp = client.get("/api/settings/vpn-network", headers=env["admin_headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode_key"] == "local_http"
    assert data["backend_port"] == "8000"
    assert data["nginx_setup_hint"] == "scripts/nginx-setup.sh"
    assert isinstance(data["env_rows"], list)
    assert len(data["env_rows"]) >= 5


def test_get_vpn_network_settings_blocked_when_disabled(vpn_disabled_api_client):
    client, env = vpn_disabled_api_client
    resp = client.get("/api/settings/vpn-network", headers=env["admin_headers"])
    assert resp.status_code == 403
    assert "отключён" in resp.json()["detail"].lower()


def test_get_vpn_network_settings_includes_publish_modes(vpn_api_client):
    client, env = vpn_api_client
    resp = client.get("/api/settings/vpn-network", headers=env["admin_headers"])
    assert resp.status_code == 200
    modes = resp.json().get("publish_modes") or []
    assert len(modes) >= 3
    keys = {m["key"] for m in modes}
    assert "nginx_le" in keys
    assert "http_direct" in keys


def test_publish_vpn_network_requires_admin(vpn_api_client):
    client, env = vpn_api_client
    payload = {"mode": "http_direct", "backend_port": 8000, "https_public_port": 443, "http_acme_port": 80}
    resp = client.post("/api/settings/vpn-network/publish", json=payload)
    assert resp.status_code == 401


def test_publish_vpn_network_ok(vpn_api_client, monkeypatch, tmp_path):
    client, env = vpn_api_client
    script = tmp_path / "nginx-setup.sh"
    script.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    script.chmod(0o755)

    monkeypatch.setattr(
        "app.services.background_tasks.PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        "app.services.background_tasks.BackgroundTaskService.run_checked_command",
        lambda self, *args, **kwargs: ("ok", ""),
    )

    payload = {
        "mode": "http_direct",
        "backend_port": 8000,
        "https_public_port": 443,
        "http_acme_port": 80,
    }
    resp = client.post("/api/settings/vpn-network/publish", json=payload, headers=env["admin_headers"])
    assert resp.status_code == 202
    data = resp.json()
    assert data["task_id"]
    assert data["task_type"] == "vpn_network_publish"


def test_publish_vpn_network_nginx_le_requires_domain(vpn_api_client):
    client, env = vpn_api_client
    payload = {"mode": "nginx_le", "backend_port": 8000, "https_public_port": 443, "http_acme_port": 80}
    resp = client.post("/api/settings/vpn-network/publish", json=payload, headers=env["admin_headers"])
    assert resp.status_code == 400


def test_publish_vpn_network_blocked_when_disabled(vpn_disabled_api_client):
    client, env = vpn_disabled_api_client
    payload = {"mode": "http_direct", "backend_port": 8000, "https_public_port": 443, "http_acme_port": 80}
    resp = client.post("/api/settings/vpn-network/publish", json=payload, headers=env["admin_headers"])
    assert resp.status_code == 403
