"""Refresh rotation: reuse of a rotated token revokes its family; concurrent tab refresh is tolerated."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database import Base
from app.models import RefreshToken, User, UserRole
from app.routers import auth as auth_router
from app.services import refresh_token as rt


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def user(db):
    row = User(username="alice", password_hash="x", role=UserRole.admin, is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _row(db, raw: str) -> RefreshToken:
    db.expire_all()
    return db.query(RefreshToken).filter(RefreshToken.token_hash == rt._hash_token(raw)).one()


def _age_revocation(db, raw: str, seconds: int) -> None:
    row = _row(db, raw)
    row.revoked_at = datetime.utcnow() - timedelta(seconds=seconds)
    db.commit()


def test_rotation_keeps_family_and_marks_old_token_rotated(db, user):
    raw, first = rt.create_refresh_token(db, user)

    new_raw, got_user = rt.rotate_refresh_token(db, raw)

    assert got_user.id == user.id
    assert new_raw and new_raw != raw
    old, new = _row(db, raw), _row(db, new_raw)
    assert old.revoked is True
    assert old.revoke_reason == "rotated"
    assert old.revoked_at is not None
    assert first.family_id and new.family_id == first.family_id
    assert new.revoked is False


def test_reuse_after_grace_revokes_whole_family_only(db, user):
    raw, _ = rt.create_refresh_token(db, user)
    other_device, _ = rt.create_refresh_token(db, user)
    new_raw, _ = rt.rotate_refresh_token(db, raw)
    _age_revocation(db, raw, rt.ROTATION_GRACE_SECONDS + 5)

    with pytest.raises(HTTPException) as exc:
        rt.rotate_refresh_token(db, raw)

    assert exc.value.status_code == 401
    assert _row(db, new_raw).revoked is True
    assert _row(db, new_raw).revoke_reason == "reuse"
    assert _row(db, other_device).revoked is False


def test_reuse_within_grace_returns_access_only_and_keeps_family(db, user):
    raw, _ = rt.create_refresh_token(db, user)
    new_raw, _ = rt.rotate_refresh_token(db, raw)

    again_raw, got_user = rt.rotate_refresh_token(db, raw)

    assert again_raw is None
    assert got_user.id == user.id
    assert _row(db, new_raw).revoked is False
    assert db.query(RefreshToken).count() == 2


def test_lost_rotation_race_issues_no_second_token(db, user, monkeypatch):
    raw, _ = rt.create_refresh_token(db, user)
    real_active_user = rt._active_user

    def concurrent_rotation(session, user_id):
        session.execute(
            text(
                "UPDATE refresh_tokens SET revoked = 1, revoke_reason = 'rotated', revoked_at = :now "
                "WHERE token_hash = :h"
            ),
            {"now": datetime.utcnow(), "h": rt._hash_token(raw)},
        )
        return real_active_user(session, user_id)

    monkeypatch.setattr(rt, "_active_user", concurrent_rotation)

    new_raw, got_user = rt.rotate_refresh_token(db, raw)

    assert not db.in_transaction(), "the lost claim must not keep the write transaction open"
    assert new_raw is None
    assert got_user.id == user.id
    assert db.query(RefreshToken).count() == 1


def test_session_revoked_during_rotation_leaves_no_live_token_in_family(tmp_path, monkeypatch):
    import threading
    import time

    from sqlalchemy import event

    from app.database import apply_sqlite_connection_pragmas

    engine = create_engine(f"sqlite:///{tmp_path / 'rt.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        apply_sqlite_connection_pragmas(cursor)
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    rotating, revoking = factory(), factory()
    try:
        owner = User(username="alice", password_hash="x", role=UserRole.admin, is_active=True)
        rotating.add(owner)
        rotating.commit()
        raw, first = rt.create_refresh_token(rotating, owner)
        family = first.family_id

        claimed, revoker_started = threading.Event(), threading.Event()
        real_create = rt.create_refresh_token

        def create_after_revoke_attempt(session, user, *, family_id=None):
            claimed.set()
            revoker_started.wait(5)
            time.sleep(0.3)
            return real_create(session, user, family_id=family_id)

        monkeypatch.setattr(rt, "create_refresh_token", create_after_revoke_attempt)
        result: dict = {}
        worker = threading.Thread(target=lambda: result.update(new=rt.rotate_refresh_token(rotating, raw)[0]))
        worker.start()
        assert claimed.wait(5)
        revoker_started.set()
        rt.revoke_token_family(revoking, family, reason="session")
        worker.join(10)

        assert result["new"]
        revoking.expire_all()
        live = revoking.query(RefreshToken).filter_by(family_id=family, revoked=False).count()
        assert live == 0, "a token issued while the session was being revoked must not survive"
    finally:
        rotating.close()
        revoking.close()
        engine.dispose()


def _legacy_token(db, user, raw: str, **fields) -> None:
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=rt._hash_token(raw),
            expires_at=datetime.utcnow() + timedelta(days=1),
            **fields,
        )
    )
    db.commit()


def test_reuse_of_rotated_legacy_token_without_family_revokes_all_user_tokens(db, user):
    _legacy_token(db, user, "legacy-token", revoked=False)
    rt.rotate_refresh_token(db, "legacy-token")
    _age_revocation(db, "legacy-token", rt.ROTATION_GRACE_SECONDS + 5)
    live_raw, _ = rt.create_refresh_token(db, user)

    with pytest.raises(HTTPException):
        rt.rotate_refresh_token(db, "legacy-token")

    assert _row(db, live_raw).revoked is True


def test_token_revoked_before_upgrade_is_rejected_without_revoking_others(db, user):
    _legacy_token(db, user, "legacy-token", revoked=True)
    live_raw, _ = rt.create_refresh_token(db, user)

    with pytest.raises(HTTPException) as exc:
        rt.rotate_refresh_token(db, "legacy-token")

    assert exc.value.status_code == 401
    assert _row(db, live_raw).revoked is False


def test_logged_out_token_is_rejected_without_revoking_other_sessions(db, user):
    raw, _ = rt.create_refresh_token(db, user)
    other_device, _ = rt.create_refresh_token(db, user)
    rt.revoke_refresh_token(db, raw)

    with pytest.raises(HTTPException):
        rt.rotate_refresh_token(db, raw)
    assert _row(db, raw).revoke_reason == "logout"
    assert _row(db, other_device).revoked is False


def test_grace_does_not_outlive_session_invalidation(db, user):
    raw, _ = rt.create_refresh_token(db, user)
    rt.rotate_refresh_token(db, raw)
    rt.invalidate_user_sessions(db, user, reason="password")

    with pytest.raises(HTTPException) as exc:
        rt.rotate_refresh_token(db, raw)
    assert exc.value.status_code == 401


def test_grace_does_not_outlive_reuse_detection(db, user):
    raw, _ = rt.create_refresh_token(db, user)
    first_rotation, _ = rt.rotate_refresh_token(db, raw)
    rt.rotate_refresh_token(db, first_rotation)
    _age_revocation(db, raw, rt.ROTATION_GRACE_SECONDS + 5)
    with pytest.raises(HTTPException):
        rt.rotate_refresh_token(db, raw)

    with pytest.raises(HTTPException):
        rt.rotate_refresh_token(db, first_rotation)


def test_invalidate_sessions_increments_current_db_version(db, user):
    assert (user.token_version or 0) == 0
    db.execute(text("UPDATE users SET token_version = 5 WHERE id = :id"), {"id": user.id})

    rt.invalidate_user_sessions(db, user, reason="password")

    assert db.execute(text("SELECT token_version FROM users WHERE id = :id"), {"id": user.id}).scalar() == 6
    assert user.token_version == 6


def test_inactive_user_cannot_use_grace(db, user):
    raw, _ = rt.create_refresh_token(db, user)
    rt.rotate_refresh_token(db, raw)
    user.is_active = False
    db.commit()

    with pytest.raises(HTTPException):
        rt.rotate_refresh_token(db, raw)


def test_migration_adds_rotation_columns_to_legacy_table(monkeypatch):
    import app.database as database
    from sqlalchemy import inspect

    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE refresh_tokens (id INTEGER PRIMARY KEY, user_id INTEGER, "
                "token_hash VARCHAR(64) UNIQUE, expires_at DATETIME, revoked BOOLEAN, created_at DATETIME)"
            )
        )
    monkeypatch.setattr(database, "engine", engine)

    database.run_db_migrations()

    columns = {col["name"] for col in inspect(engine).get_columns("refresh_tokens")}
    assert {"family_id", "revoked_at", "revoke_reason"} <= columns
    assert "ix_refresh_tokens_family_id" in {idx["name"] for idx in inspect(engine).get_indexes("refresh_tokens")}


def test_refresh_route_in_grace_does_not_overwrite_cookie(db, user):
    raw, _ = rt.create_refresh_token(db, user)
    rt.rotate_refresh_token(db, raw)
    request = MagicMock()
    request.cookies = {get_settings().refresh_token_cookie_name: raw}
    response = Response()

    token = auth_router.refresh_token(request, response, db)

    assert token.access_token
    assert "set-cookie" not in response.headers


def test_refresh_route_failure_clears_cookie(db, user):
    raw, _ = rt.create_refresh_token(db, user)
    rt.revoke_refresh_token(db, raw)
    cookie_name = get_settings().refresh_token_cookie_name
    request = MagicMock()
    request.cookies = {cookie_name: raw}

    result = auth_router.refresh_token(request, Response(), db)

    assert result.status_code == 401
    set_cookie = result.headers.get("set-cookie", "")
    assert set_cookie.startswith(f"{cookie_name}=") and "Max-Age=0" in set_cookie
