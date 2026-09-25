"""Mini App tokens must work only in /tg-mini and the panel routes the Mini App actually calls."""

from unittest.mock import MagicMock

import jwt
import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import (
    create_access_token,
    create_tg_mini_token,
    get_active_user_from_access_token,
    get_current_user,
    tg_mini_token_allowed,
)
from app.config import get_settings
from app.database import Base, get_db
from app.models import User, UserRole
from app.routers.tg_mini import TelegramAuthRequest, tg_auth


@pytest.fixture
def db_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all(
        [
            User(username="bob", password_hash="x", role=UserRole.admin, is_active=True, telegram_id="555"),
            User(username="relinked", password_hash="x", role=UserRole.admin, is_active=True, telegram_id="999"),
        ]
    )
    db.commit()
    db.close()
    yield factory
    engine.dispose()


def _db_override(db_factory):
    def _get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    return _get_db


@pytest.fixture
def client(db_factory):
    router = APIRouter(prefix="/configs")

    @router.get("/quota")
    @tg_mini_token_allowed
    def quota(user: User = Depends(get_current_user)):
        return {"user": user.username}

    @router.get("/export")
    def export(user: User = Depends(get_current_user)):
        return {"user": user.username}

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = _db_override(db_factory)
    return TestClient(app)


def _call(client: TestClient, method: str, path: str, token: str):
    return client.request(method, path, headers={"Authorization": f"Bearer {token}"})


def test_tg_mini_token_allowed_on_marked_endpoint(client):
    response = _call(client, "GET", "/api/configs/quota", create_tg_mini_token("bob", "555"))
    assert response.status_code == 200
    assert response.json() == {"user": "bob"}


def test_tg_mini_token_rejected_on_unmarked_endpoint(client):
    response = _call(client, "GET", "/api/configs/export", create_tg_mini_token("bob", "555"))
    assert response.status_code == 401


def test_access_token_still_works_on_unmarked_endpoint(client):
    response = _call(client, "GET", "/api/configs/export", create_access_token({"sub": "bob"}))
    assert response.status_code == 200


def test_tg_mini_token_rejected_after_telegram_relink(client):
    response = _call(client, "GET", "/api/configs/quota", create_tg_mini_token("relinked", "555"))
    assert response.status_code == 401


def test_tg_mini_token_is_not_a_panel_access_token(db_factory):
    db = db_factory()
    try:
        assert get_active_user_from_access_token(db, create_tg_mini_token("bob", "555")) is None
    finally:
        db.close()


# Calls made by frontend/src/tg-mini/api.ts (panelApiFetch) and a sample of /tg-mini routes.
_MINI_APP_CALLS = [
    ("GET", "/api/tg-mini/dashboard"),
    ("GET", "/api/configs/quota"),
    ("GET", "/api/configs/999"),
    ("POST", "/api/configs"),
    ("PATCH", "/api/configs/999"),
    ("DELETE", "/api/configs/999"),
    ("GET", "/api/users"),
    ("GET", "/api/client-templates"),
    ("POST", "/api/client-templates/999/apply"),
    ("GET", "/api/client-access/policies"),
    *(
        ("POST", f"/api/client-access/{proto}/{action}")
        for proto in ("openvpn", "wireguard")
        for action in ("temp-block", "permanent-block", "unblock")
    ),
    *(("POST", f"/api/client-access/{proto}/set-traffic-limit") for proto in ("openvpn", "wireguard", "amneziawg2")),
    *(("PATCH", f"/api/client-access/{proto}/c1/access-until") for proto in ("openvpn", "wireguard", "amneziawg2")),
    ("GET", "/api/unlock-codes"),
    ("POST", "/api/unlock-codes"),
    ("POST", "/api/unlock-codes/999/revoke"),
]

_PANEL_ONLY_CALLS = [
    ("GET", "/api/configs"),
    ("GET", "/api/configs/export"),
    ("DELETE", "/api/users/2"),
    ("POST", "/api/client-access/openvpn/disconnect"),
    ("POST", "/api/client-templates"),
]


@pytest.fixture
def real_client(db_factory):
    from app.routers import client_access, client_templates, configs, tg_mini, unlock_codes, users

    app = FastAPI()
    for module in (configs, users, client_templates, client_access, unlock_codes, tg_mini):
        app.include_router(module.router, prefix="/api")
    app.dependency_overrides[get_db] = _db_override(db_factory)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(("method", "path"), _MINI_APP_CALLS)
def test_real_mini_app_routes_accept_tg_mini_token(real_client, method, path):
    response = _call(real_client, method, path, create_tg_mini_token("bob", "555"))
    assert response.status_code != 401, response.text


@pytest.mark.parametrize(("method", "path"), _PANEL_ONLY_CALLS)
def test_real_panel_routes_reject_tg_mini_token(real_client, method, path):
    response = _call(real_client, method, path, create_tg_mini_token("bob", "555"))
    assert response.status_code == 401


def _patch_tg_auth(monkeypatch, init_user: dict):
    monkeypatch.setattr("app.routers.tg_mini._get_bot_token", lambda _db: "bot:token")
    monkeypatch.setattr("app.routers.tg_mini._get_setting", lambda _db, _key, default="": "300")
    monkeypatch.setattr("app.routers.tg_mini._verify_telegram_init_data", lambda *_a, **_k: init_user)
    notify = MagicMock()
    monkeypatch.setattr("app.routers.tg_mini.admin_notify_service.send_tg_login_unlinked", notify)
    monkeypatch.setattr("app.routers.tg_mini.ip_restriction_service.get_client_ip", lambda _req: "127.0.0.1")
    monkeypatch.setattr("app.routers.tg_mini.get_client_timezone_from_request", lambda _req: None)
    return notify


def test_tg_auth_issues_scoped_mini_app_token(monkeypatch, db_factory):
    _patch_tg_auth(monkeypatch, {"id": 555})
    db = db_factory()
    try:
        result = tg_auth(payload=TelegramAuthRequest(init_data="x"), request=MagicMock(), db=db)
    finally:
        db.close()
    settings = get_settings()
    payload = jwt.decode(result["access_token"], settings.secret_key, algorithms=[settings.algorithm])
    assert payload["type"] == "tg_mini"
    assert payload["sub"] == "bob"
    assert payload["tg"] == "555"


def test_tg_auth_rejects_init_data_without_user_id(monkeypatch):
    notify = _patch_tg_auth(monkeypatch, {})
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        tg_auth(payload=TelegramAuthRequest(init_data="x"), request=MagicMock(), db=db)
    assert exc.value.status_code == 401
    db.query.assert_not_called()
    notify.assert_not_called()


def test_tg_auth_rejects_inactive_user(monkeypatch, db_factory):
    _patch_tg_auth(monkeypatch, {"id": 555})
    db = db_factory()
    try:
        db.query(User).filter(User.username == "bob").update({"is_active": False})
        db.commit()
        with pytest.raises(HTTPException) as exc:
            tg_auth(payload=TelegramAuthRequest(init_data="x"), request=MagicMock(), db=db)
    finally:
        db.close()
    assert exc.value.status_code == 401
