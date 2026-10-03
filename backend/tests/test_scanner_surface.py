"""What an unauthenticated scanner sees: no fingerprint, no map of admin paths, no 200 on probe paths."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.database import Base, get_db
from app.middleware.http_security import build_robots_txt, is_scanner_probe_path
from app.models import User, UserRole
from app.routers import feature_toggles
from app.services.health_checks import build_light_health


def test_light_health_has_no_fingerprint():
    assert set(build_light_health()) == {"status", "started_at"}


def test_robots_txt_does_not_list_panel_paths():
    assert build_robots_txt() == "User-agent: *\nDisallow: /\n"


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".git/config",
        ".vite/manifest.json",
        "app/.htaccess",
        "wp-login.php",
        "backup.sql",
        "config.yml",
        "phpmyadmin/",
        "server-status",
        "wp-admin/install",
        "cgi-bin/test",
    ],
)
def test_probe_paths_are_detected(path):
    assert is_scanner_probe_path(path)


@pytest.mark.parametrize("path", ["", "login", "configs", "settings/security", "p/abc123", "traffic/client/alice"])
def test_spa_routes_are_not_probes(path):
    assert not is_scanner_probe_path(path)


@pytest.fixture
def modules_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add(User(username="alice", password_hash="x", role=UserRole.user, is_active=True))
    db.commit()
    db.close()

    def override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(feature_toggles.feature_modules_router)
    app.dependency_overrides[get_db] = override_db
    yield TestClient(app)
    engine.dispose()


def test_feature_modules_requires_login(modules_client):
    assert modules_client.get("/feature-modules").status_code == 401


def test_feature_modules_for_logged_in_user(modules_client):
    token = create_access_token({"sub": "alice"})
    response = modules_client.get("/feature-modules", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "features" in response.json()


def test_feature_modules_accepts_mini_app_token():
    assert getattr(feature_toggles.get_feature_modules, "_tg_mini_token_allowed", False)


def test_telegram_login_config_reports_disabled_module(monkeypatch):
    from types import SimpleNamespace

    from app.routers import auth as auth_router
    from app.services import feature_guards

    monkeypatch.setattr(feature_guards, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda _key: False))
    payload = auth_router.telegram_login_config(request=None, db=None)
    assert payload["module_enabled"] is False
    assert payload["enabled"] is False
