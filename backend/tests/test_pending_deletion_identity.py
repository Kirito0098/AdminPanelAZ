"""A user pending deletion must not hold its username, base name or Telegram id."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserRole
from app.routers import users as users_router
from app.services import user_identity_conflict
from app.schemas import UserCreate
from app.services.telegram_link import create_link_code, redeem_link_code

PASSWORD = "Str0ng-pass-1"


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    try:
        yield make
    finally:
        engine.dispose()


def _stubs(monkeypatch) -> list[tuple[int, str]]:
    enqueued: list[tuple[int, str]] = []
    stub = lambda _db, *, user_id, actor_username: enqueued.append((user_id, actor_username))
    monkeypatch.setattr(user_identity_conflict, "enqueue_user_delete_cleanup", stub)
    monkeypatch.setattr(users_router, "enqueue_user_delete_cleanup", stub)
    monkeypatch.setattr(users_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(users_router.admin_notify_service, "send_user_create", lambda *_a, **_k: None)
    return enqueued


def test_create_user_restarts_cleanup_instead_of_saying_user_exists(factory, monkeypatch):
    enqueued = _stubs(monkeypatch)
    with factory() as db:
        ghost = User(
            username="test",
            password_hash="x",
            role=UserRole.user,
            provision_state="pending_deletion",
        )
        admin = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
        db.add_all([ghost, admin])
        db.commit()
        ghost_id = ghost.id

        with pytest.raises(HTTPException) as excinfo:
            users_router.create_user(
                UserCreate(username="test", password=PASSWORD, role=UserRole.user),
                MagicMock(),
                db=db,
                admin=admin,
            )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "user_deletion_pending"
    assert enqueued == [(ghost_id, "admin")]


def test_redeem_link_code_ignores_telegram_of_a_pending_deletion_user(factory):
    with factory() as db:
        ghost = User(
            username="test",
            password_hash="x",
            role=UserRole.user,
            telegram_id="555",
            provision_state="pending_deletion",
        )
        carol = User(username="carol", password_hash="x", role=UserRole.user)
        db.add_all([ghost, carol])
        db.commit()
        carol_id = carol.id

        code, _ttl = create_link_code(db, carol)
        ok, message, user = redeem_link_code(db, code, "555")

    assert ok is True, message
    assert user is not None and user.id == carol_id


def test_redeem_link_code_still_refuses_telegram_of_an_active_user(factory):
    with factory() as db:
        owner = User(username="owner", password_hash="x", role=UserRole.user, telegram_id="555")
        carol = User(username="carol", password_hash="x", role=UserRole.user)
        db.add_all([owner, carol])
        db.commit()

        code, _ttl = create_link_code(db, carol)
        ok, _message, user = redeem_link_code(db, code, "555")

    assert (ok, user) == (False, None)
