"""Disabling a user ends every session, and re-enabling does not revive them."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import (
    _get_active_user_from_tg_mini_token,
    create_tg_mini_token,
    create_user_access_token,
    get_password_hash,
)
from app.database import Base, get_db
from app.models import ActiveWebSession, RefreshToken, User, UserRole
from app.routers import auth as auth_router
from app.routers import users as users_router
from app.services import refresh_token as rt


@pytest.fixture
def db_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all(
        [
            User(username="admin", password_hash=get_password_hash("x-admin-1"), role=UserRole.admin, is_active=True),
            User(
                username="carol",
                password_hash=get_password_hash("x-carol-1"),
                role=UserRole.user,
                is_active=True,
                telegram_id="777",
            ),
        ]
    )
    db.commit()
    db.close()
    yield factory
    engine.dispose()


@pytest.fixture
def client(db_factory):
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


def _user(db, username: str) -> User:
    return db.query(User).filter(User.username == username).one()


def test_disable_then_enable_keeps_old_sessions_dead(client, db_factory):
    db = db_factory()
    admin_token = create_user_access_token(_user(db, "admin"))
    carol = _user(db, "carol")
    carol_id = carol.id
    raw_refresh, _ = rt.create_refresh_token(db, carol, family_id="sess-carol")
    carol_access = create_user_access_token(carol, session_id="sess-carol")
    carol_mini = create_tg_mini_token("carol", "777", token_version=carol.token_version or 0)
    now = datetime.utcnow()
    db.add(ActiveWebSession(session_id="sess-carol", username="carol", created_at=now, last_seen_at=now))
    db.commit()
    db.close()
    auth = {"Authorization": f"Bearer {admin_token}"}

    assert client.patch(f"/api/users/{carol_id}", json={"is_active": False}, headers=auth).status_code == 200
    assert client.patch(f"/api/users/{carol_id}", json={"is_active": True}, headers=auth).status_code == 200

    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {carol_access}"}).status_code == 401
    db = db_factory()
    try:
        tokens = db.query(RefreshToken).filter(RefreshToken.user_id == carol_id).all()
        assert tokens and all(row.revoked for row in tokens)
        assert {row.revoke_reason for row in tokens} == {"disabled"}
        assert db.query(ActiveWebSession).filter_by(session_id="sess-carol").one().revoked_at is not None
        assert _get_active_user_from_tg_mini_token(db, carol_mini) is None
    finally:
        db.close()


def test_saving_other_fields_of_active_user_keeps_sessions(client, db_factory):
    db = db_factory()
    admin_token = create_user_access_token(_user(db, "admin"))
    carol = _user(db, "carol")
    carol_id = carol.id
    carol_access = create_user_access_token(carol)
    db.close()

    response = client.patch(
        f"/api/users/{carol_id}",
        json={"is_active": True, "theme": "light"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {carol_access}"}).status_code == 200
