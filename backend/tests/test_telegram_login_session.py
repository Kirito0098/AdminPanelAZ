"""Website Telegram login opens a full, revocable web session like password login does."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.auth import get_active_user_from_access_token
from app.config import get_settings
from app.database import Base
from app.models import ActiveWebSession, RefreshToken, User, UserRole
from app.routers import auth as auth_router
from app.routers import security as security_router
from app.schemas import TelegramOidcTokenRequest
from app.services import refresh_token as rt

settings = get_settings()


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setattr(settings, "active_web_session_tracking_enabled", True)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def user(db):
    row = User(username="tg-alice", password_hash="x", role=UserRole.admin, is_active=True, telegram_id="777")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/telegram",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("10.0.0.7", 50000),
            "query_string": b"",
        }
    )


def _cookie(response: Response) -> str:
    header = response.headers["set-cookie"]
    name, value = header.split(";", 1)[0].split("=", 1)
    assert name == settings.refresh_token_cookie_name
    return value


def _assert_full_session(db, access: str, session_id: str, cookie: str, username: str) -> None:
    claims = jwt.decode(access, settings.secret_key, algorithms=[settings.algorithm])
    assert claims["sid"] == session_id
    assert db.query(ActiveWebSession).filter_by(session_id=session_id).one().username == username
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == rt._hash_token(cookie)).one()
    assert row.family_id == session_id


def test_telegram_redirect_sets_refresh_cookie_and_passes_the_session_id(db, user):
    response = auth_router._telegram_login_redirect(user, db, _request())

    assert response.status_code == 302
    location = urlsplit(response.headers["location"])
    assert location.path.endswith("/login")
    params = parse_qs(location.fragment)
    access, session_id = params["token"][0], params["session"][0]
    assert list(params) == ["token", "session"]
    _assert_full_session(db, access, session_id, _cookie(response), "tg-alice")


def test_telegram_redirect_session_can_be_revoked(db, user):
    response = auth_router._telegram_login_redirect(user, db, _request())
    params = parse_qs(urlsplit(response.headers["location"]).fragment)

    security_router.revoke_active_session(params["session"][0], db=db, _=user)

    assert get_active_user_from_access_token(db, params["token"][0]) is None
    with pytest.raises(Exception):
        rt.rotate_refresh_token(db, _cookie(response))


@pytest.mark.parametrize("endpoint", ["widget", "oidc_callback"])
def test_both_redirect_endpoints_open_a_session(db, user, monkeypatch, endpoint):
    class _Features:
        def is_enabled(self, _name):
            return True

    monkeypatch.setattr("app.services.feature_guards.get_feature_service", lambda: _Features())
    monkeypatch.setattr(auth_router, "_complete_telegram_login", lambda _db, _req, _tg, mini=False: user)
    if endpoint == "widget":
        monkeypatch.setattr(auth_router, "_get_telegram_auth_settings", lambda _db: ("bot", "name", 86400))
        monkeypatch.setattr(auth_router, "_legacy_login_enabled", lambda _db: True)
        monkeypatch.setattr(auth_router, "_verify_telegram_login", lambda *_a: (True, ""))
        response = auth_router.telegram_login_callback(_request(), db)
    else:
        monkeypatch.setattr(auth_router, "_get_telegram_oidc_settings", lambda _db: (True, "cid", "secret"))
        monkeypatch.setattr(auth_router, "pop_oidc_state", lambda _s: {"redirect_uri": "x", "code_verifier": "v"})
        monkeypatch.setattr(auth_router, "exchange_authorization_code", lambda **_k: {"id_token": "idt"})
        monkeypatch.setattr(auth_router, "verify_id_token", lambda *_a, **_k: {"sub": "777"})
        monkeypatch.setattr(auth_router, "telegram_id_from_claims", lambda _c: "777")
        request = _request()
        request.scope["query_string"] = b"code=c&state=s"
        response = auth_router.telegram_oidc_callback(request, db)

    params = parse_qs(urlsplit(response.headers["location"]).fragment)
    _assert_full_session(db, params["token"][0], params["session"][0], _cookie(response), "tg-alice")


def test_oidc_token_endpoint_returns_a_session_and_sets_the_cookie(db, user, monkeypatch):
    class _Features:
        def is_enabled(self, _name):
            return True

    monkeypatch.setattr("app.services.feature_guards.get_feature_service", lambda: _Features())
    monkeypatch.setattr(auth_router, "_get_telegram_oidc_settings", lambda _db: (True, "cid", "secret"))
    monkeypatch.setattr(auth_router, "verify_id_token", lambda *_a, **_k: {"sub": "777"})
    monkeypatch.setattr(auth_router, "telegram_id_from_claims", lambda _c: "777")
    monkeypatch.setattr(auth_router, "_complete_telegram_login", lambda _db, _req, _tg, mini=False: user)
    response = Response()

    result = auth_router.telegram_oidc_token(TelegramOidcTokenRequest(id_token="i" * 32), _request(), response, db)

    assert result.token_type == "bearer"
    _assert_full_session(db, result.access_token, result.web_session_id, _cookie(response), "tg-alice")
