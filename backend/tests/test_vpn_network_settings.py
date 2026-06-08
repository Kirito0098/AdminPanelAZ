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
