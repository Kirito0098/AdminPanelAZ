"""Tests for health endpoints."""

from fastapi.testclient import TestClient


def test_light_health(api_test_env):
    client = TestClient(api_test_env["app"])
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"]
    assert "started_at" in body


def test_deep_health(api_test_env):
    client = TestClient(api_test_env["app"])
    response = client.get("/api/health/deep")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "checks" in body
    assert "main_db" in body["checks"]
    assert "cidr_db" in body["checks"]
    assert "traffic_sync" in body["checks"]
