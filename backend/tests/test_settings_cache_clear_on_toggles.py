"""Settings lru_cache cleared after feature toggle / profile writes."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.models import User
from app.routers import feature_toggles as feature_toggles_router
from app.services.feature_toggles import FeatureToggleService


def _build_client(monkeypatch, service: FeatureToggleService, *, cache_clear: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(feature_toggles_router.router)

    def override_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[feature_toggles_router.require_admin] = lambda: User(
        id=1,
        username="admin",
        role="admin",
    )

    # Patch the symbols the router module actually binds.
    monkeypatch.setattr(feature_toggles_router, "get_feature_service", lambda: service)

    mocked_get_settings = MagicMock()
    mocked_get_settings.cache_clear = cache_clear
    monkeypatch.setattr(feature_toggles_router, "get_settings", mocked_get_settings)

    return TestClient(app)


def test_update_feature_toggles_clears_settings_cache(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_TELEGRAM_ENABLED=true\n", encoding="utf-8")
    service = FeatureToggleService(env_file)
    cache_clear = MagicMock()
    client = _build_client(monkeypatch, service, cache_clear=cache_clear)

    response = client.put("/feature-toggles", json={"toggles": {"telegram": False}})

    assert response.status_code == 200
    cache_clear.assert_called_once()


def test_apply_resource_profile_clears_settings_cache(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_TELEGRAM_ENABLED=true\n", encoding="utf-8")
    service = FeatureToggleService(env_file)
    cache_clear = MagicMock()
    client = _build_client(monkeypatch, service, cache_clear=cache_clear)

    response = client.post("/feature-toggles/apply-profile?profile=minimal")

    assert response.status_code == 200
    cache_clear.assert_called_once()
