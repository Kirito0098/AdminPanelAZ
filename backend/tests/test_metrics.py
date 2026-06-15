"""Tests for Prometheus /metrics endpoint."""

from fastapi.testclient import TestClient


def test_metrics_endpoint(api_test_env):
    client = TestClient(api_test_env["app"])
    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "traffic_collector_lag_seconds" in text
    assert "node_health_online_total" in text
    assert "node_health_nodes_total" in text
