"""The asset marker cookie follows the web session: issued with it, renewed on refresh, dropped on logout."""

from __future__ import annotations

import pytest
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.config import get_settings
from app.database import Base
from app.models import User, UserRole
from app.routers import auth as auth_router
from app.services import refresh_token as rt
from app.services.asset_marker import ASSET_MARKER_COOKIE, asset_marker_valid

settings = get_settings()


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def admin(db):
    row = User(username="alice", password_hash="x", role=UserRole.admin, is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _request(*, cookie: str | None = None, https: bool = False) -> Request:
    headers = [(b"user-agent", b"pytest")]
    if cookie is not None:
        headers.append((b"cookie", f"{settings.refresh_token_cookie_name}={cookie}".encode()))
    if https:
        headers.append((b"x-forwarded-proto", b"https"))
    return Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("testserver", 80),
            "method": "POST",
            "path": "/api/auth/login",
            "headers": headers,
            "client": ("10.0.0.5", 50000),
            "query_string": b"",
        }
    )


def _marker_header(response: Response) -> str:
    found = [h for h in response.headers.getlist("set-cookie") if h.startswith(f"{ASSET_MARKER_COOKIE}=")]
    assert len(found) == 1, response.headers.getlist("set-cookie")
    return found[0]


def _attrs(header: str) -> set[str]:
    return {part.strip().lower() for part in header.split(";")[1:]}


def _value(header: str) -> str:
    return header.split(";", 1)[0].split("=", 1)[1]


def test_login_sets_marker_after_the_refresh_cookie(db, admin):
    response = Response()

    auth_router._issue_token_pair(admin, db, response, _request())

    assert response.headers.getlist("set-cookie")[0].startswith(f"{settings.refresh_token_cookie_name}=")
    header = _marker_header(response)
    attrs = _attrs(header)
    assert {"httponly", "path=/assets", "samesite=strict"} <= attrs
    assert f"max-age={settings.refresh_token_expire_days * 86400}" in attrs
    assert "secure" not in attrs
    assert asset_marker_valid(settings.secret_key, _value(header))


def test_marker_is_secure_over_https(db, admin):
    response = Response()

    auth_router._issue_token_pair(admin, db, response, _request(https=True))

    assert "secure" in _attrs(_marker_header(response))


def test_marker_path_follows_access_path(db, admin, monkeypatch):
    monkeypatch.setattr(settings, "access_path", "/panel")
    response = Response()

    auth_router._issue_token_pair(admin, db, response, _request())

    assert "path=/panel/assets" in _attrs(_marker_header(response))


def test_refresh_renews_the_marker(db, admin):
    login = Response()
    auth_router._issue_token_pair(admin, db, login, _request())
    refresh_cookie = _value(login.headers.getlist("set-cookie")[0])
    renewed = Response()

    token = auth_router.refresh_token(_request(cookie=refresh_cookie), renewed, db)

    assert token.access_token
    assert asset_marker_valid(settings.secret_key, _value(_marker_header(renewed)))


def test_refused_refresh_drops_the_marker(db, admin):
    raw, _ = rt.create_refresh_token(db, admin)
    rt.revoke_refresh_token(db, raw)

    result = auth_router.refresh_token(_request(cookie=raw), Response(), db)

    assert result.status_code == 401
    assert {"max-age=0", "path=/assets"} <= _attrs(_marker_header(result))


def test_logout_drops_the_marker(db, admin):
    response = Response()

    auth_router.logout(_request(), response, db)

    assert {"max-age=0", "path=/assets"} <= _attrs(_marker_header(response))


def test_session_check_issues_the_marker(admin):
    response = Response()

    user = auth_router.me(_request(), response, admin)

    assert user is admin
    assert asset_marker_valid(settings.secret_key, _value(_marker_header(response)))
