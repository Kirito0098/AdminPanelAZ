"""A password change must end every session issued before it, except the one that changed it."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import (
    _get_active_user_from_tg_mini_token,
    create_access_token,
    create_tg_mini_token,
    create_user_access_token,
    get_active_user_from_access_token,
    get_password_hash,
    verify_password,
)
from app.database import Base, get_db
from app.models import RefreshToken, User, UserRole
from app.routers import auth as auth_router
from app.routers import users as users_router
from app.services import refresh_token as rt

OLD_PASSWORD = "Old-password-1"
NEW_PASSWORD = "New-password-2x"


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
                password_hash=get_password_hash(OLD_PASSWORD),
                role=UserRole.admin,
                is_active=True,
                telegram_id="555",
            ),
            User(username="carol", password_hash=get_password_hash(OLD_PASSWORD), role=UserRole.user, is_active=True),
        ]
    )
    db.commit()
    db.close()
    yield factory
    engine.dispose()


@pytest.fixture
def client(db_factory, monkeypatch):
    monkeypatch.setattr(auth_router, "should_scrub_env_after_password_change", lambda _username: False)
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


def _user(db_factory, username: str) -> tuple[object, User]:
    db = db_factory()
    return db, db.query(User).filter(User.username == username).one()


def _token_for(db_factory, username: str) -> str:
    db, user = _user(db_factory, username)
    try:
        return create_user_access_token(user)
    finally:
        db.close()


def _me(client: TestClient, token: str) -> int:
    return client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code


def _change_own_password(client: TestClient, token: str):
    return client.post(
        "/api/auth/change-password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_change_password_rejects_old_access_tokens_and_returns_new_session(client, db_factory):
    old_token = _token_for(db_factory, "admin")
    other_device = create_access_token({"sub": "admin"})

    response = _change_own_password(client, old_token)

    assert response.status_code == 200
    new_token = response.json()["access_token"]
    assert "set-cookie" in response.headers
    assert _me(client, old_token) == 401
    assert _me(client, other_device) == 401
    assert _me(client, new_token) == 200


def test_change_password_revokes_old_refresh_tokens_but_issues_one(client, db_factory):
    db, admin = _user(db_factory, "admin")
    old_refresh, _ = rt.create_refresh_token(db, admin)
    db.close()

    response = _change_own_password(client, _token_for(db_factory, "admin"))

    assert response.status_code == 200
    db, admin = _user(db_factory, "admin")
    rows = db.query(RefreshToken).filter(RefreshToken.user_id == admin.id).all()
    live = [row for row in rows if not row.revoked]
    assert len(live) == 1
    assert live[0].token_hash != rt._hash_token(old_refresh)
    db.close()


def test_change_password_rejects_old_tg_mini_token(client, db_factory):
    mini = create_tg_mini_token("admin", "555")

    assert _change_own_password(client, _token_for(db_factory, "admin")).status_code == 200

    db = db_factory()
    assert _get_active_user_from_tg_mini_token(db, mini) is None
    db.close()


def test_admin_password_reset_ends_target_sessions_only(client, db_factory):
    admin_token = _token_for(db_factory, "admin")
    carol_token = _token_for(db_factory, "carol")
    db, carol = _user(db_factory, "carol")
    carol_id = carol.id
    db.close()

    response = client.patch(
        f"/api/users/{carol_id}",
        json={"password": NEW_PASSWORD},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert _me(client, carol_token) == 401
    assert _me(client, admin_token) == 200


@pytest.mark.parametrize("username", ["admin", "carol"])
def test_own_password_cannot_be_changed_through_the_user_card(client, db_factory, username):
    token = _token_for(db_factory, username)
    db, user = _user(db_factory, username)
    user_id, theme = user.id, user.theme
    db.close()

    response = client.patch(
        f"/api/users/{user_id}",
        json={"password": NEW_PASSWORD, "theme": "light"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "текущ" in response.json()["detail"]
    assert _me(client, token) == 200
    db, user = _user(db_factory, username)
    assert verify_password(OLD_PASSWORD, user.password_hash)
    assert user.theme == theme
    db.close()


def test_own_card_without_password_still_saves(client, db_factory):
    token = _token_for(db_factory, "carol")
    db, carol = _user(db_factory, "carol")
    carol_id = carol.id
    db.close()

    response = client.patch(f"/api/users/{carol_id}", json={"theme": "light"}, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["theme"] == "light"
    assert _me(client, token) == 200


def test_legacy_token_without_version_valid_until_first_change(db_factory):
    legacy = create_access_token({"sub": "carol"})
    db, carol = _user(db_factory, "carol")

    assert get_active_user_from_access_token(db, legacy) is not None
    rt.invalidate_user_sessions(db, carol, reason="password")
    assert get_active_user_from_access_token(db, legacy) is None
    assert get_active_user_from_access_token(db, create_user_access_token(carol)) is not None
    db.close()


def test_stream_and_docs_token_checks_reject_stale_tokens(db_factory):
    from app.routers import awg2, monitoring, warper
    from app.services import openapi_docs_gate

    stale = _token_for(db_factory, "admin")
    db, admin = _user(db_factory, "admin")
    rt.invalidate_user_sessions(db, admin, reason="password")

    with pytest.raises(HTTPException):
        monitoring._user_from_access_token(stale, db)
    with pytest.raises(HTTPException):
        awg2._admin_from_stream_token(stale, db)
    with pytest.raises(HTTPException):
        warper._admin_from_stream_token(stale, db)
    assert openapi_docs_gate._is_admin_token(stale, db) is False
    assert openapi_docs_gate._is_admin_token(create_user_access_token(admin), db) is True
    db.close()


def test_active_session_middleware_ignores_stale_token(db_factory, monkeypatch):
    from unittest.mock import MagicMock

    from app.middleware import active_session

    touch = MagicMock()
    monkeypatch.setattr(active_session, "SessionLocal", db_factory)
    monkeypatch.setattr(active_session.active_web_session_service, "touch_active_web_session", touch)
    app = FastAPI()
    app.add_middleware(active_session.ActiveSessionMiddleware)

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    with db_factory() as db:
        admin = db.query(User).filter(User.username == "admin").one()
        stale = create_user_access_token(admin)
        rt.invalidate_user_sessions(db, admin, reason="password")
        current = create_user_access_token(admin)

    client = TestClient(app)
    client.get("/api/ping", headers={"Authorization": f"Bearer {stale}", "X-Web-Session-Id": "sess-1"})
    assert touch.call_count == 0

    client.get("/api/ping", headers={"Authorization": f"Bearer {current}", "X-Web-Session-Id": "sess-1"})
    assert touch.call_count == 1
    assert touch.call_args.args[1] == "admin"
