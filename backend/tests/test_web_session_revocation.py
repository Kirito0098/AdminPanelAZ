"""Revoking a web session ends it on the server: its access and refresh tokens stop working."""

from __future__ import annotations

from datetime import datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.auth import get_active_user_from_access_token, get_password_hash
from app.config import get_settings
from app.database import Base
from app.models import ActiveWebSession, RefreshToken, User, UserRole
from app.routers import auth as auth_router
from app.routers import security as security_router
from app.schemas import PasswordChangeRequest
from app.services import refresh_token as rt
from app.services.active_web_session import active_web_session_service

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
def admin(db):
    row = User(
        username="alice",
        password_hash=get_password_hash("Old-Passw0rd!x"),
        role=UserRole.admin,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _request(*, cookie: str | None = None, bearer: str | None = None) -> Request:
    headers = [(b"user-agent", b"pytest")]
    if cookie is not None:
        headers.append((b"cookie", f"{settings.refresh_token_cookie_name}={cookie}".encode()))
    if bearer is not None:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": headers,
            "client": ("10.0.0.5", 50000),
            "query_string": b"",
        }
    )


def _login(db, user):
    response = Response()
    token = auth_router._issue_token_pair(user, db, response, _request())
    cookie = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    return token, cookie


def _claims(access: str) -> dict:
    return jwt.decode(access, settings.secret_key, algorithms=[settings.algorithm])


def _family(db, raw: str) -> str | None:
    db.expire_all()
    return db.query(RefreshToken).filter(RefreshToken.token_hash == rt._hash_token(raw)).one().family_id


def _refresh(db, cookie: str) -> tuple[int, str | None, str | None]:
    response = Response()
    result = auth_router.refresh_token(_request(cookie=cookie), response, db)
    if isinstance(result, Response):
        return result.status_code, None, None
    new_cookie = None
    if "set-cookie" in response.headers:
        new_cookie = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    return 200, result.access_token, new_cookie


def test_login_ties_access_token_and_refresh_family_to_the_web_session(db, admin):
    token, cookie = _login(db, admin)

    assert token.web_session_id
    assert _claims(token.access_token)["sid"] == token.web_session_id
    assert _family(db, cookie) == token.web_session_id
    assert db.query(ActiveWebSession).filter_by(session_id=token.web_session_id).one().username == "alice"


def test_revoked_session_access_token_is_rejected_other_sessions_keep_working(db, admin):
    revoked, _ = _login(db, admin)
    other, _ = _login(db, admin)

    security_router.revoke_active_session(revoked.web_session_id, db=db, _=admin)

    assert get_active_user_from_access_token(db, revoked.access_token) is None
    assert get_active_user_from_access_token(db, other.access_token).username == "alice"


def test_revoked_session_cannot_refresh_and_is_not_treated_as_theft(db, admin):
    revoked, revoked_cookie = _login(db, admin)
    other, other_cookie = _login(db, admin)

    security_router.revoke_active_session(revoked.web_session_id, db=db, _=admin)

    status, access, _ = _refresh(db, revoked_cookie)
    assert (status, access) == (401, None)
    db.expire_all()
    reasons = {row.revoke_reason for row in db.query(RefreshToken).filter_by(family_id=revoked.web_session_id)}
    assert reasons == {"session"}
    status, access, _ = _refresh(db, other_cookie)
    assert status == 200
    assert _claims(access)["sid"] == other.web_session_id


def test_refresh_keeps_the_session_id_in_new_access_tokens(db, admin):
    token, cookie = _login(db, admin)

    status, access, new_cookie = _refresh(db, cookie)
    assert status == 200
    assert _claims(access)["sid"] == token.web_session_id

    security_router.revoke_active_session(token.web_session_id, db=db, _=admin)
    assert get_active_user_from_access_token(db, access) is None
    assert _refresh(db, new_cookie)[0] == 401


def test_revoking_unknown_session_is_404_and_touches_no_tokens(db, admin):
    _, cookie = _login(db, admin)

    with pytest.raises(HTTPException) as exc:
        security_router.revoke_active_session("f" * 32, db=db, _=admin)

    assert exc.value.status_code == 404
    assert _refresh(db, cookie)[0] == 200


def test_revoked_session_outlives_stale_cleanup_until_its_access_tokens_expire(db, admin):
    token, _ = _login(db, admin)
    security_router.revoke_active_session(token.web_session_id, db=db, _=admin)
    row = db.query(ActiveWebSession).filter_by(session_id=token.web_session_id).one()
    now = datetime.utcnow()
    row.last_seen_at = now - timedelta(days=2)
    row.revoked_at = now - timedelta(minutes=settings.access_token_expire_minutes - 1)
    db.commit()

    active_web_session_service.cleanup_stale_active_web_sessions(db, now=now)
    active_web_session_service.cleanup_stale_for_nightly(db)
    db.commit()
    assert get_active_user_from_access_token(db, token.access_token) is None

    row.revoked_at = now - timedelta(minutes=settings.access_token_expire_minutes + 1)
    db.commit()
    active_web_session_service.cleanup_stale_active_web_sessions(db, now=now)
    db.commit()
    assert db.query(ActiveWebSession).filter_by(session_id=token.web_session_id).count() == 0


def test_nightly_cleanup_also_keeps_recently_revoked_sessions(db, admin):
    token, _ = _login(db, admin)
    security_router.revoke_active_session(token.web_session_id, db=db, _=admin)
    row = db.query(ActiveWebSession).filter_by(session_id=token.web_session_id).one()
    row.last_seen_at = datetime.utcnow() - timedelta(days=3)
    db.commit()

    active_web_session_service.cleanup_stale_for_nightly(db)

    assert db.query(ActiveWebSession).filter_by(session_id=token.web_session_id).count() == 1


def test_password_change_keeps_the_tab_bound_to_its_session(db, admin, monkeypatch):
    monkeypatch.setattr(auth_router, "should_scrub_env_after_password_change", lambda _username: False)
    monkeypatch.setattr(auth_router.settings, "audit_log_enabled", False)
    token, _ = _login(db, admin)
    response = Response()

    result = auth_router.change_password(
        PasswordChangeRequest(current_password="Old-Passw0rd!x", new_password="New-Passw0rd!y"),
        _request(bearer=token.access_token),
        response,
        db=db,
        current_user=admin,
        token=token.access_token,
    )

    new_cookie = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    assert _claims(result.access_token)["sid"] == token.web_session_id
    assert _family(db, new_cookie) == token.web_session_id
    security_router.revoke_active_session(token.web_session_id, db=db, _=admin)
    assert get_active_user_from_access_token(db, result.access_token) is None
    assert _refresh(db, new_cookie)[0] == 401


def test_tokens_without_a_session_id_still_work(db, admin):
    from app.auth import create_access_token

    legacy = create_access_token({"sub": "alice", "role": "admin", "tv": 0})

    assert get_active_user_from_access_token(db, legacy).username == "alice"
