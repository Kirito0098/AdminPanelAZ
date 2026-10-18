"""Stage 1 Task 7: `panel_login_enabled` auth gate.

Password / refresh / passkey / Telegram OIDC panel login is rejected when
`panel_login_enabled=False` (same 401 as wrong credentials); Mini App is exempt;
disabling the flag bumps `token_version` and revokes user sessions.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import (
    assert_panel_login_allowed,
    create_2fa_pending_token,
    create_user_access_token,
    get_password_hash,
)
from app.database import Base, get_db
from app.models import ActiveWebSession, User, UserRole
from app.routers import auth as auth_router
from app.routers import users as users_router
from app.config import get_settings
from app.services.active_web_session import active_web_session_service
from app.services.refresh_token import create_refresh_token

settings = get_settings()


@pytest.fixture
def db_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all(
        [
            User(
                username="admin",
                password_hash=get_password_hash("admin-secret"),
                role=UserRole.admin,
                is_active=True,
            ),
            User(
                username="ivan",
                password_hash=get_password_hash("ivan-secret"),
                role=UserRole.user,
                is_active=True,
                panel_login_enabled=True,
            ),
            User(
                username="no-panel",
                password_hash=get_password_hash("no-panel-secret"),
                role=UserRole.user,
                is_active=True,
                panel_login_enabled=False,
                telegram_id="111",
            ),
        ]
    )
    db.commit()
    db.close()
    yield factory
    engine.dispose()


@pytest.fixture
def client(db_factory, monkeypatch):
    monkeypatch.setattr(auth_router, "should_scrub_env_after_password_change", lambda _username: False)
    monkeypatch.setattr(users_router.admin_notify_service, "send_user_create", lambda *_a, **_k: None)
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api")
    app.include_router(users_router.router, prefix="/api")

    def _get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _token(db_factory, username: str) -> str:
    with db_factory() as db:
        return create_user_access_token(db.query(User).filter(User.username == username).one())


def _auth(username: str, db_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(db_factory, username)}"}


def _set_panel_login(db_factory, username: str, value: bool) -> None:
    with db_factory() as db:
        user = db.query(User).filter(User.username == username).one()
        user.panel_login_enabled = value
        db.commit()


def _panel_state(db_factory, username: str):
    with db_factory() as db:
        user = db.query(User).filter(User.username == username).one()
        return user.token_version, user.panel_login_enabled


def _request_stub():
    from types import SimpleNamespace

    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})


def test_assert_panel_login_allowed_enabled_passes():
    user = User(username="ivan", panel_login_enabled=True)
    assert_panel_login_allowed(user, mini=False)  # does not raise


def test_assert_panel_login_allowed_disabled_rejects():
    user = User(username="no-panel", panel_login_enabled=False)
    with pytest.raises(HTTPException) as exc:
        assert_panel_login_allowed(user, mini=False)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc.value.detail == "Неверный логин или пароль"


def test_assert_panel_login_allowed_mini_exempt():
    user = User(username="no-panel", panel_login_enabled=False)
    assert_panel_login_allowed(user, mini=True)  # Mini App is not gated


def test_password_login_rejected_like_bad_credentials(client, db_factory):
    _set_panel_login(db_factory, "no-panel", False)
    response = client.post(
        "/api/auth/login/json",
        json={"username": "no-panel", "password": "no-panel-secret"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Неверный логин или пароль"


def test_password_login_ok_when_enabled(client):
    response = client.post("/api/auth/login/json", json={"username": "ivan", "password": "ivan-secret"})
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()


def test_refresh_rejected_when_panel_login_disabled(client, db_factory):
    _set_panel_login(db_factory, "no-panel", False)
    with db_factory() as db:
        user = db.query(User).filter(User.username == "no-panel").one()
        raw, _ = create_refresh_token(db, user)
    client.cookies.set(settings.refresh_token_cookie_name, raw)
    response = client.post("/api/auth/refresh")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Неверный логин или пароль"


def test_passkey_login_rejected_when_panel_login_disabled(client, db_factory, monkeypatch):
    _set_panel_login(db_factory, "no-panel", False)
    monkeypatch.setattr(auth_router, "user_has_passkeys", lambda _db, _user: True)
    monkeypatch.setattr(auth_router.webauthn_service, "authentication_verify", MagicMock())
    temp_token = create_2fa_pending_token("no-panel")
    response = client.post(
        "/api/auth/login/passkey/verify",
        json={"temp_token": temp_token, "credential": {}, "session_key": "x"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Неверный логин или пароль"


def test_telegram_login_rejected_when_panel_login_disabled(db_factory):
    from app.routers.auth import _complete_telegram_login

    with db_factory() as db:
        user = db.query(User).filter(User.username == "no-panel").one()
        assert user.panel_login_enabled is False
        with pytest.raises(HTTPException) as exc:
            _complete_telegram_login(db, _request_stub(), "111", mini=False)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc.value.detail == "Неверный логин или пароль"


def test_disable_bumps_token_version_and_revokes_sessions(client, db_factory):
    admin_headers = _auth("admin", db_factory)
    with db_factory() as db:
        ivan = db.query(User).filter(User.username == "ivan").one()
        ivan_id = ivan.id
        db.add(ActiveWebSession(session_id="sess-1", username="ivan", last_seen_at=datetime.utcnow()))
        raw, _ = create_refresh_token(db, ivan)
        db.commit()

    response = client.patch(
        f"/api/users/{ivan_id}",
        json={"panel_login_enabled": False},
        headers=admin_headers,
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()["panel_login_enabled"] is False

    token_version, panel_login_enabled = _panel_state(db_factory, "ivan")
    assert panel_login_enabled is False
    assert token_version == 1

    with db_factory() as db:
        session_row = db.query(ActiveWebSession).filter_by(session_id="sess-1").one()
        assert session_row.revoked_at is not None
