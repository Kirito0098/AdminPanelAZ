"""Tests for feature guard middleware."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_ROUTING_ENABLED=false\nTRAFFIC_SYNC_ENABLED=false\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: __import__("app.services.feature_toggles", fromlist=["FeatureToggleService"]).FeatureToggleService(env_file),
    )

    from app.main import app

    return TestClient(app)


def test_feature_modules_endpoint(client):
    resp = client.get("/api/feature-modules")
    assert resp.status_code == 200
    data = resp.json()
    assert "features" in data
    assert data["features"]["routing"] is False


def test_blocked_routing_api_returns_403(client):
    resp = client.get("/api/routing/overview")
    assert resp.status_code == 403
    body = resp.json()
    assert body["feature_disabled"] == "routing"


def test_allowed_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
