"""Tests for resource profile presets."""

from pathlib import Path

from app.services.feature_toggles import FeatureToggleService, RESOURCE_PROFILES


def test_apply_minimal_profile_disables_heavy_toggles(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TRAFFIC_SYNC_ENABLED=true\nRESOURCE_PROFILE=full\n", encoding="utf-8")
    service = FeatureToggleService(env_file)

    result = service.apply_resource_profile("minimal")

    assert result["profile"] == "minimal"
    assert service.get_resource_profile() == "minimal"
    assert service.is_enabled("traffic_sync") is False
    assert service.is_enabled("routing") is False
    assert service.is_enabled("server_monitor") is False
    assert service.env.get_env_value("RESOURCE_METRICS_ENABLED") == "false"
    assert service.env.get_env_value("CIDR_DB_REFRESH_ENABLED") == "false"


def test_list_resource_profiles(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RESOURCE_PROFILE=standard\n", encoding="utf-8")
    service = FeatureToggleService(env_file)
    payload = service.list_resource_profiles()
    assert payload["current_profile"] == "standard"
    assert len(payload["items"]) == len(RESOURCE_PROFILES)


def test_apply_profile_api(api_test_env, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.services.feature_toggles import FeatureToggleService

    env_file = tmp_path / ".env"
    env_file.write_text("RESOURCE_PROFILE=full\n", encoding="utf-8")
    service = FeatureToggleService(env_file)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", lambda: service)

    client = TestClient(api_test_env["app"])
    headers = api_test_env["admin_headers"]
    response = client.post("/api/feature-toggles/apply-profile?profile=minimal", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["profile"] == "minimal"
    assert body["requires_restart"] is True
