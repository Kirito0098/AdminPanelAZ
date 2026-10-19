"""Stage 5 Task 4: scenario preset API.

Routes (admin only): GET /presets, POST /preview-preset, POST /apply-preset,
GET /current-preset. The legacy /profiles, /apply-profile and /current-profile
routes are gone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import require_admin
from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import feature_toggles as feature_toggles_router
from app.services.feature_toggles import FeatureToggleService


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(
        User(
            username="admin",
            password_hash="not-used",
            role=UserRole.admin,
            is_active=True,
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def env_path(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text(
        "SCENARIO_PRESET=home\nFEATURE_TELEGRAM_ENABLED=false\n",
        encoding="utf-8",
    )
    return path


def _client(db_session, env_path, monkeypatch, *, admin: bool) -> TestClient:
    app = FastAPI()
    app.include_router(feature_toggles_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    if admin:
        app.dependency_overrides[require_admin] = lambda: db_session.query(User).first()
    service = FeatureToggleService(env_path)
    monkeypatch.setattr(feature_toggles_router, "get_feature_service", lambda: service)
    return TestClient(app)


@pytest.fixture
def client(db_session, env_path, monkeypatch):
    return _client(db_session, env_path, monkeypatch, admin=False)


@pytest.fixture
def admin_client(db_session, env_path, monkeypatch):
    return _client(db_session, env_path, monkeypatch, admin=True)


def test_list_presets_requires_admin(client):
    r = client.get("/api/feature-toggles/presets")
    assert r.status_code in (401, 403)


def test_preview_and_apply_preset(admin_client, env_path, db_session):
    from app.services.user_grace import get_grace_months

    r = admin_client.post("/api/feature-toggles/preview-preset?preset=commercial")
    assert r.status_code == 200
    body = r.json()
    assert "will_enable" in body and "summary_ru" in body
    # Preview diffs AppSetting grace (default 0) → commercial 3.
    assert body["settings_changes"]["inactive_user_grace_period_months"]["to"] == 3

    r2 = admin_client.post("/api/feature-toggles/apply-preset?preset=commercial")
    assert r2.status_code == 200
    assert r2.json()["preset"] == "commercial"
    assert get_grace_months(db_session) == 3

    r3 = admin_client.post("/api/feature-toggles/apply-preset?preset=panel_only")
    assert r3.status_code == 200
    assert r3.json()["preset"] == "panel_only"
    assert get_grace_months(db_session) == 0
    cur = admin_client.get("/api/feature-toggles/current-preset")
    assert cur.json()["preset"] in ("panel_only", "custom")
    assert "SCENARIO_PRESET=panel_only" in env_path.read_text(encoding="utf-8")


def test_list_presets_payload(admin_client):
    r = admin_client.get("/api/feature-toggles/presets")
    assert r.status_code == 200
    body = r.json()
    assert {item["key"] for item in body["items"]} == {"panel_only", "home", "commercial"}
    assert body["current_preset"] in ("panel_only", "home", "commercial", "custom")
    assert body["resolved"]["is_custom"] in (True, False)
    assert body["requires_restart"] is True


def test_unknown_preset_rejected(admin_client):
    r = admin_client.post("/api/feature-toggles/preview-preset?preset=minimal")
    assert r.status_code == 400
    r2 = admin_client.post("/api/feature-toggles/apply-preset?preset=minimal")
    assert r2.status_code == 400


def test_legacy_profile_routes_removed(admin_client):
    assert admin_client.get("/api/feature-toggles/profiles").status_code == 404
    assert admin_client.post("/api/feature-toggles/apply-profile?profile=full").status_code == 404
    assert admin_client.get("/api/feature-toggles/current-profile").status_code == 404
