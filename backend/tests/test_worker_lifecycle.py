"""Tests for worker startup plan (resource profiles)."""

from pathlib import Path

from app.services.feature_toggles import FeatureToggleService
from app.services.lifespan_workers import get_worker_startup_plan
from app.services.worker_lifecycle import (
    should_start_cidr_scheduler,
    should_start_traffic_collector,
)


def _minimal_env(tmp_path: Path) -> FeatureToggleService:
    service = FeatureToggleService(tmp_path / ".env")
    service.apply_resource_profile("minimal")
    return service


def test_minimal_profile_disables_heavy_workers(tmp_path, monkeypatch):
    service = _minimal_env(tmp_path)
    monkeypatch.setattr("app.services.worker_lifecycle.get_feature_service", lambda: service)
    monkeypatch.setenv("TRAFFIC_SYNC_ENABLED", "false")
    monkeypatch.setenv("RESOURCE_METRICS_ENABLED", "false")
    monkeypatch.setenv("PANEL_RESOURCE_METRICS_ENABLED", "false")
    monkeypatch.setenv("NODE_HEALTH_SYNC_ENABLED", "false")
    monkeypatch.setenv("CIDR_DB_REFRESH_ENABLED", "false")
    monkeypatch.setenv("CERT_SYNC_ENABLED", "false")
    monkeypatch.setenv("MONITOR_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()

    plan = get_worker_startup_plan()
    assert plan["traffic_collector"] is False
    assert plan["node_health"] is False
    assert plan["resource_metrics"] is False
    assert plan["panel_resource_metrics"] is False
    assert plan["cidr_scheduler"] is False
    assert plan["resource_monitor"] is False
    assert should_start_traffic_collector() is False


def test_full_profile_enables_core_workers(tmp_path, monkeypatch):
    service = FeatureToggleService(tmp_path / ".env")
    service.apply_resource_profile("full")
    monkeypatch.setattr("app.services.worker_lifecycle.get_feature_service", lambda: service)
    monkeypatch.setenv("TRAFFIC_SYNC_ENABLED", "true")
    monkeypatch.setenv("RESOURCE_METRICS_ENABLED", "true")
    monkeypatch.setenv("PANEL_RESOURCE_METRICS_ENABLED", "true")
    monkeypatch.setenv("NODE_HEALTH_SYNC_ENABLED", "true")
    monkeypatch.setenv("CIDR_DB_REFRESH_ENABLED", "true")
    monkeypatch.setenv("CERT_SYNC_ENABLED", "true")
    monkeypatch.setenv("MONITOR_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()

    plan = get_worker_startup_plan()
    assert plan["traffic_collector"] is True
    assert plan["cidr_scheduler"] is True
    assert should_start_traffic_collector() is True
    assert should_start_cidr_scheduler() is True
