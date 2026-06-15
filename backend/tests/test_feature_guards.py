"""Tests for feature guard middleware."""

import pytest
from fastapi.testclient import TestClient


def _feature_service_factory(env_file):
    def factory():
        return __import__(
            "app.services.feature_toggles", fromlist=["FeatureToggleService"]
        ).FeatureToggleService(env_file)

    return factory


@pytest.fixture()
def client(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_ROUTING_ENABLED=false\nTRAFFIC_SYNC_ENABLED=false\n", encoding="utf-8")

    service_factory = _feature_service_factory(env_file)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", service_factory)
    monkeypatch.setattr("app.routers.feature_toggles.get_feature_service", service_factory)

    from app.main import app

    return TestClient(app)


@pytest.fixture()
def guarded_client(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "FEATURE_USER_MANAGEMENT_ENABLED=false",
                "FEATURE_ACTION_LOGS_ENABLED=false",
                "FEATURE_SYSTEM_UPDATES_ENABLED=false",
                "FEATURE_QR_DOWNLOADS_ENABLED=false",
                "FEATURE_AMNEZIAWG_ENABLED=false",
                "FEATURE_WIREGUARD_ENABLED=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    service_factory = _feature_service_factory(env_file)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", service_factory)
    monkeypatch.setattr("app.routers.feature_toggles.get_feature_service", service_factory)

    from app.main import app

    return TestClient(app)


def test_feature_modules_endpoint(client):
    resp = client.get("/api/feature-modules")
    assert resp.status_code == 200
    data = resp.json()
    assert "features" in data
    assert data["features"]["routing"] is False
    assert "amneziawg" in data["features"]
    assert data["settings_tabs"]["users"] == "user_management"
    assert data["settings_tabs"]["monitoring"] == "resource_monitor"


def test_blocked_routing_api_returns_403(client):
    resp = client.get("/api/routing/overview")
    assert resp.status_code == 403
    body = resp.json()
    assert body["feature_disabled"] == "routing"


def test_blocked_warper_api_returns_403(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_WARPER_ENABLED=false\n", encoding="utf-8")
    service_factory = _feature_service_factory(env_file)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", service_factory)
    monkeypatch.setattr("app.routers.feature_toggles.get_feature_service", service_factory)

    from app.main import app as test_app

    client = TestClient(test_app)
    resp = client.get("/api/warper/health")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "warper"


def test_blocked_cidr_db_status_returns_403(client):
    resp = client.get("/api/routing/cidr-db/status")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "routing"


def test_allowed_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_blocked_users_when_user_management_disabled(guarded_client):
    resp = guarded_client.get("/api/users")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "user_management"


def test_blocked_action_logs_when_disabled(guarded_client):
    resp = guarded_client.get("/api/logs/actions")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "action_logs"

    resp_export = guarded_client.get("/api/logs/action-logs/export")
    assert resp_export.status_code == 403
    assert resp_export.json()["feature_disabled"] == "action_logs"


def test_blocked_system_updates_when_disabled(guarded_client):
    resp = guarded_client.get("/api/system/updates")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "system_updates"


def test_blocked_config_download_when_qr_downloads_disabled(guarded_client):
    resp = guarded_client.get("/api/configs/1/download?path=/tmp/x.conf")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "qr_downloads"


def test_wireguard_api_allowed_when_amneziawg_disabled_but_wireguard_enabled(guarded_client):
    resp = guarded_client.get("/api/client-access/wireguard/alice")
    if resp.status_code == 403:
        assert resp.json().get("feature_disabled") not in {"wireguard", "amneziawg"}


@pytest.fixture()
def maintenance_disabled_client(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_MAINTENANCE_ENABLED=false\n", encoding="utf-8")

    service_factory = _feature_service_factory(env_file)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", service_factory)
    monkeypatch.setattr("app.routers.feature_toggles.get_feature_service", service_factory)

    from app.main import app

    return TestClient(app)


def test_blocked_maintenance_run_doall_when_disabled(maintenance_disabled_client):
    resp = maintenance_disabled_client.post("/api/settings/run-doall")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "maintenance"


def test_blocked_maintenance_restart_service_when_disabled(maintenance_disabled_client):
    resp = maintenance_disabled_client.post(
        "/api/settings/restart-service",
        json={"service_name": "openvpn-server@antizapret-udp"},
    )
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "maintenance"


def test_blocked_maintenance_recreate_profiles_when_disabled(maintenance_disabled_client):
    resp = maintenance_disabled_client.post("/api/settings/recreate-profiles")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "maintenance"


def test_blocked_maintenance_session_stats_when_disabled(maintenance_disabled_client):
    resp = maintenance_disabled_client.get("/api/maintenance/session-stats")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "maintenance"


def test_feature_modules_includes_maintenance_tab(maintenance_disabled_client):
    resp = maintenance_disabled_client.get("/api/feature-modules")
    assert resp.status_code == 200
    data = resp.json()
    assert data["features"]["maintenance"] is False
    assert data["settings_tabs"]["maintenance"] == "maintenance"


def test_blocked_tg_mini_when_telegram_disabled(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_TELEGRAM_ENABLED=false\n", encoding="utf-8")
    service_factory = _feature_service_factory(env_file)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", service_factory)
    monkeypatch.setattr("app.routers.feature_toggles.get_feature_service", service_factory)

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/tg-mini")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "telegram"
