"""Accounts whose password an admin set must change it before using the panel API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_tg_mini_token, create_user_access_token, get_password_hash
from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import auth as auth_router
from app.routers import configs as configs_router
from app.routers import session as session_router
from app.routers import users as users_router
from app.services.self_service import set_self_service_limits

ADMIN_SET_PASSWORD = "Given-by-admin-1"
OWN_PASSWORD = "Own-password-2x"


@pytest.fixture
def db_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all(
        [
            User(username="admin", password_hash=get_password_hash(OWN_PASSWORD), role=UserRole.admin, is_active=True),
            User(
                username="carol",
                password_hash=get_password_hash(ADMIN_SET_PASSWORD),
                role=UserRole.user,
                is_active=True,
                telegram_id="777",
                must_change_password=True,
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
    for module in (auth_router, users_router, configs_router, session_router):
        app.include_router(module.router, prefix="/api")

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


def _flag(db_factory, username: str) -> bool:
    with db_factory() as db:
        return db.query(User).filter(User.username == username).one().must_change_password


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("required", [True, False])
def test_admin_set_password_follows_setting(client, db_factory, required):
    with db_factory() as db:
        set_self_service_limits(db, require_password_change=required)
        carol = db.query(User).filter(User.username == "carol").one()
        carol.must_change_password = False
        carol_id = carol.id
        db.commit()
    admin = _auth(_token(db_factory, "admin"))

    created = client.post("/api/users", json={"username": "dave", "password": ADMIN_SET_PASSWORD}, headers=admin)
    reset = client.patch(f"/api/users/{carol_id}", json={"password": ADMIN_SET_PASSWORD}, headers=admin)

    assert created.status_code == 201
    assert reset.status_code == 200
    assert _flag(db_factory, "dave") is required
    assert _flag(db_factory, "carol") is required


def test_flagged_web_session_is_blocked_until_password_change(client, db_factory):
    token = _token(db_factory, "carol")

    blocked = client.get("/api/configs/quota", headers=_auth(token))
    assert blocked.status_code == 403
    assert blocked.json()["detail"].startswith("password_change_required")
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200

    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": ADMIN_SET_PASSWORD, "new_password": OWN_PASSWORD},
        headers=_auth(token),
    )
    assert changed.status_code == 200
    new_token = changed.json()["access_token"]
    assert client.get("/api/configs/quota", headers=_auth(new_token)).status_code == 200


def test_flagged_session_keeps_heartbeat_to_learn_about_revocation(client, db_factory):
    response = client.get("/api/session-heartbeat", headers=_auth(_token(db_factory, "carol")))

    assert response.status_code == 200


def test_reusing_admin_set_password_does_not_clear_flag(client, db_factory):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": ADMIN_SET_PASSWORD, "new_password": ADMIN_SET_PASSWORD},
        headers=_auth(_token(db_factory, "carol")),
    )

    assert response.status_code == 400
    assert _flag(db_factory, "carol") is True


def test_flagged_user_keeps_mini_app_access(client):
    response = client.get("/api/configs/quota", headers=_auth(create_tg_mini_token("carol", "777")))
    assert response.status_code == 200
