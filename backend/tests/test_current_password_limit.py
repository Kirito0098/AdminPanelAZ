"""Current-password checks reuse the login limiter, keyed per user and shared by both endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.auth as app_auth
from app.auth import create_user_access_token, get_password_hash, verify_password
from app.config import get_settings
from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import auth as auth_router
from app.routers import telegram_webhook
from app.services.app_setting_store import _set_setting
from app.services.auth_rate_limit import AuthRateLimitService

PASSWORD = "Carol-pass-1"
NEW_PASSWORD = "Carol-new-pass-2"
MAX_ATTEMPTS = 3
LOCKED_DETAIL = "Слишком много попыток ввода пароля. Повторите позже."


class _Features:
    def is_enabled(self, _name):
        return True


@pytest.fixture(autouse=True)
def limiter(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "auth_rate_limit_backend", "memory")
    monkeypatch.setattr(settings, "auth_rate_limit_max_attempts", MAX_ATTEMPTS)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 300)
    monkeypatch.setattr(app_auth, "auth_rate_limit_service", AuthRateLimitService())


@pytest.fixture
def db_factory(monkeypatch):
    monkeypatch.setattr(telegram_webhook, "get_feature_service", lambda: _Features())
    monkeypatch.setattr(auth_router, "should_scrub_env_after_password_change", lambda _username: False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all(
        [
            User(username="carol", password_hash=get_password_hash(PASSWORD), role=UserRole.user, is_active=True),
            User(username="erin", password_hash=get_password_hash(PASSWORD), role=UserRole.user, is_active=True),
        ]
    )
    _set_setting(db, "telegram_bot_token", "bot:token")
    db.commit()
    db.close()
    yield factory
    engine.dispose()


@pytest.fixture
def client(db_factory):
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api")
    app.include_router(telegram_webhook.router, prefix="/api")

    def _get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _auth(db_factory, username: str) -> dict[str, str]:
    db = db_factory()
    try:
        user = db.query(User).filter(User.username == username).one()
        return {"Authorization": f"Bearer {create_user_access_token(user)}"}
    finally:
        db.close()


def _change_password(client, headers, current: str):
    return client.post(
        "/api/auth/change-password",
        json={"current_password": current, "new_password": NEW_PASSWORD},
        headers=headers,
    )


def _link_code(client, headers, current: str):
    return client.post("/api/telegram/link-code", json={"current_password": current}, headers=headers)


def test_change_password_locks_after_repeated_wrong_passwords(client, db_factory):
    headers = _auth(db_factory, "carol")
    for _ in range(MAX_ATTEMPTS):
        assert _change_password(client, headers, "wrong").status_code == 400

    locked = _change_password(client, headers, PASSWORD)

    assert locked.status_code == 429
    assert locked.json()["detail"] == LOCKED_DETAIL
    assert locked.headers["Retry-After"] == "300"
    db = db_factory()
    try:
        carol = db.query(User).filter(User.username == "carol").one()
        assert verify_password(PASSWORD, carol.password_hash)
    finally:
        db.close()


def test_link_code_locks_after_repeated_wrong_passwords(client, db_factory):
    headers = _auth(db_factory, "carol")
    for _ in range(MAX_ATTEMPTS):
        assert _link_code(client, headers, "wrong").status_code == 400

    locked = _link_code(client, headers, PASSWORD)

    assert locked.status_code == 429
    assert locked.json()["detail"] == LOCKED_DETAIL


def test_both_endpoints_share_one_counter(client, db_factory):
    headers = _auth(db_factory, "carol")
    assert _change_password(client, headers, "wrong").status_code == 400
    assert _link_code(client, headers, "wrong").status_code == 400
    assert _change_password(client, headers, "wrong").status_code == 400

    assert _link_code(client, headers, PASSWORD).status_code == 429


def test_lock_is_per_user(client, db_factory):
    carol = _auth(db_factory, "carol")
    for _ in range(MAX_ATTEMPTS):
        _link_code(client, carol, "wrong")

    assert _link_code(client, _auth(db_factory, "erin"), PASSWORD).status_code == 200


def test_correct_password_resets_counter(client, db_factory):
    headers = _auth(db_factory, "carol")
    for _ in range(MAX_ATTEMPTS - 1):
        assert _link_code(client, headers, "wrong").status_code == 400
    assert _link_code(client, headers, PASSWORD).status_code == 200

    for _ in range(MAX_ATTEMPTS - 1):
        assert _link_code(client, headers, "wrong").status_code == 400
    assert _link_code(client, headers, PASSWORD).status_code == 200
