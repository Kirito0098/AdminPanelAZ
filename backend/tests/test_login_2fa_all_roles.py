"""A second factor enabled by any role is asked for at password login."""

from __future__ import annotations

import pytest
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.auth import create_2fa_pending_token, get_password_hash
from app.database import Base
from app.models import User, UserRole
from app.routers import auth as auth_router
from app.schemas import Login2FARequired, Token

PASSWORD = "Passw0rd-123"


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setattr(auth_router.admin_notify_service, "send_login_success", lambda *_a, **_k: None)
    monkeypatch.setattr(auth_router.settings, "audit_log_enabled", False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login/json",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("10.0.0.9", 50000),
            "query_string": b"",
        }
    )


def _add_user(db, role: UserRole, *, totp: bool = False) -> User:
    user = User(
        username="carol",
        password_hash=get_password_hash(PASSWORD),
        role=role,
        is_active=True,
        totp_enabled=totp,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(db):
    return auth_router._login_with_checks(db, _request(), "carol", PASSWORD, response=Response())


@pytest.mark.parametrize("role", [UserRole.admin, UserRole.user])
def test_password_login_asks_totp_for_every_role(db, role):
    _add_user(db, role, totp=True)

    assert isinstance(_login(db), Login2FARequired)


def test_password_login_asks_passkey_for_user_role(db, monkeypatch):
    _add_user(db, UserRole.user)
    monkeypatch.setattr(auth_router, "user_has_passkeys", lambda _db, _user_id: True)

    result = _login(db)

    assert isinstance(result, Login2FARequired)
    assert result.passkey_available is True


def test_user_without_second_factor_gets_tokens(db):
    _add_user(db, UserRole.user)

    assert isinstance(_login(db), Token)


def test_pending_2fa_token_accepted_for_user_role(db):
    user = _add_user(db, UserRole.user, totp=True)

    resolved = auth_router._user_from_2fa_token(db, create_2fa_pending_token("carol"), "10.0.0.9")

    assert resolved.id == user.id
