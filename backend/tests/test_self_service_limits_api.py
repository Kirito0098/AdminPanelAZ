from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_current_user
from app.database import Base, get_db
from app.models import UserRole
from app.routers import settings as settings_router
from app.routers import settings_telegram as settings_telegram_router
from app.routers.tg_mini import settings as tg_mini_settings_router
from app.services import self_service as ss


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'limits_api.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


def _user(role):
    return SimpleNamespace(id=1, username="admin", role=role, telegram_id="777")


def _make_client(session_factory, role=UserRole.admin):
    app = FastAPI()
    app.include_router(settings_router.router, prefix="/api")
    app.include_router(settings_telegram_router.router, prefix="/api")
    app.include_router(tg_mini_settings_router.router, prefix="/api/tg-mini")

    def _db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: _user(role)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _no_notify():
    with (
        patch("app.routers.settings.admin_notify_service"),
        patch("app.routers.settings_telegram.admin_notify_service"),
    ):
        yield


@pytest.mark.parametrize("base", ["/api/settings/self-service", "/api/tg-mini/self-service"])
def test_get_defaults(session_factory, base):
    resp = _make_client(session_factory).get(base)
    assert resp.status_code == 200
    assert resp.json() == {"quota_default": 5, "create_rate_max": 3, "create_rate_window_seconds": 3600}


@pytest.mark.parametrize("base", ["/api/settings/self-service", "/api/tg-mini/self-service"])
def test_patch_partial_persists(session_factory, base):
    client = _make_client(session_factory)
    resp = client.patch(base, json={"quota_default": 0, "create_rate_window_seconds": 600})
    assert resp.status_code == 200
    assert resp.json() == {"quota_default": 0, "create_rate_max": 3, "create_rate_window_seconds": 600}
    db = session_factory()
    try:
        assert ss.get_self_service_limits(db)["create_rate_window_seconds"] == 600
    finally:
        db.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"quota_default": 1001},
        {"quota_default": -1},
        {"create_rate_max": 101},
        {"create_rate_window_seconds": 59},
        {"create_rate_window_seconds": 86401},
    ],
)
def test_patch_out_of_bounds_422(session_factory, payload):
    resp = _make_client(session_factory).patch("/api/settings/self-service", json=payload)
    assert resp.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/settings/self-service"),
        ("patch", "/api/settings/self-service"),
        ("get", "/api/tg-mini/self-service"),
        ("patch", "/api/tg-mini/self-service"),
    ],
)
def test_non_admin_forbidden(session_factory, method, path):
    client = _make_client(session_factory, role=UserRole.user)
    resp = client.request(method, path, json={"quota_default": 1} if method == "patch" else None)
    assert resp.status_code == 403


def test_patch_notifies_settings_change(session_factory):
    with patch("app.routers.settings.admin_notify_service") as notify:
        _make_client(session_factory).patch("/api/settings/self-service", json={"create_rate_max": 7})
    notify.send_settings_change.assert_called_once()
    assert notify.send_settings_change.call_args.kwargs["settings_key"] == "settings_self_service_limits_update"


@pytest.mark.parametrize("base", ["/api/settings/telegram", "/api/tg-mini/telegram-settings"])
def test_telegram_settings_bot_rate_fields(session_factory, base):
    client = _make_client(session_factory)
    body = client.get(base).json()
    assert body["bot_command_rate_max"] == 30
    assert body["bot_command_rate_window_seconds"] == 60
    assert body["bot_command_rate_limit_enabled"] is True

    resp = client.patch(base, json={"bot_command_rate_max": 0, "bot_command_rate_window_seconds": 120})
    assert resp.status_code == 200
    assert resp.json()["bot_command_rate_max"] == 0
    assert resp.json()["bot_command_rate_window_seconds"] == 120


@pytest.mark.parametrize(
    "payload",
    [
        {"bot_command_rate_max": 1001},
        {"bot_command_rate_window_seconds": 9},
        {"bot_command_rate_window_seconds": 3601},
    ],
)
def test_telegram_settings_bot_rate_bounds_422(session_factory, payload):
    resp = _make_client(session_factory).patch("/api/settings/telegram", json=payload)
    assert resp.status_code == 422
