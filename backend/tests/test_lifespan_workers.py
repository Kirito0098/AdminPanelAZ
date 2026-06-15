"""Tests that lifespan does not spawn traffic collector under minimal profile."""

from unittest.mock import MagicMock

import pytest

from app.services.feature_toggles import FeatureToggleService
from app.services.lifespan_workers import spawn_background_tasks


@pytest.fixture()
def minimal_profile_env(tmp_path, monkeypatch):
    service = FeatureToggleService(tmp_path / ".env")
    service.apply_resource_profile("minimal")
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
    return tmp_path


def test_spawn_background_tasks_skips_traffic_under_minimal(minimal_profile_env, monkeypatch):
    created: list[str] = []

    def fake_create_task(coro):
        name = getattr(coro, "__name__", repr(coro))
        created.append(name)
        task = MagicMock()
        task.cancel = MagicMock()
        return task

    app_root = minimal_profile_env
    db_path = app_root / "data.db"
    env_path = minimal_profile_env / ".env"

    tasks = spawn_background_tasks(
        app_root=app_root,
        db_path=db_path,
        env_path=env_path,
        create_task=fake_create_task,
    )

    assert "traffic_collector" not in tasks
    assert not any("traffic" in name for name in created)
