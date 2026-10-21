"""Stage 2 Task 7: access request submit + anti-abuse (D8).

TDD: ожидаем FAIL до реализации сервиса, затем PASS.
Покрытие: приём выключен по умолчанию, один pending на TG+тип, кулдаун 24 ч,
глобальный лимит, бан, привязка для add_config/extend.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, TelegramRequestBan, User, UserAccessRequest, UserRole
from app.services.app_setting_store import _set_setting
from app.services.user_access_requests import (
    AlreadyHasAccess,
    AlreadyPending,
    Banned,
    CooldownActive,
    NotBound,
    RequestsClosed,
    submit_access_request,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def enable_new_user_requests(db):
    _set_setting(db, "telegram_accept_access_requests", "true")
    db.commit()


@pytest.fixture()
def bound_user(db):
    user = User(
        username="ivan",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        telegram_id="555",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def bound_user_111(db):
    user = User(
        username="ivan111",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        telegram_id="111",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_new_user_requests_off_by_default(db):
    with pytest.raises(RequestsClosed):
        submit_access_request(db, request_type="new_user", telegram_id="111")


def test_one_pending_per_telegram_and_type(db, enable_new_user_requests, bound_user_111):
    submit_access_request(db, request_type="new_user", telegram_id="222")
    with pytest.raises(AlreadyPending):
        submit_access_request(db, request_type="new_user", telegram_id="222")
    # Другой тип для того же Telegram — можно (пользователь привязан).
    submit_access_request(
        db, request_type="add_config", telegram_id="111", user_id=bound_user_111.id
    )


def test_new_user_rejected_for_bound_telegram(db, enable_new_user_requests, bound_user):
    """Привязанный Telegram не может подать new_user повторно — заявка не создаётся."""
    with pytest.raises(AlreadyHasAccess):
        submit_access_request(db, request_type="new_user", telegram_id=bound_user.telegram_id)
    assert db.query(UserAccessRequest).count() == 0


def test_reject_cooldown_24h(db, enable_new_user_requests):
    req = submit_access_request(db, request_type="new_user", telegram_id="222")
    req.status = "rejected"
    req.reviewed_at = datetime.utcnow()
    db.commit()
    with pytest.raises(CooldownActive):
        submit_access_request(db, request_type="new_user", telegram_id="222")
    req.reviewed_at = datetime.utcnow() - timedelta(hours=25)
    db.commit()
    submit_access_request(db, request_type="new_user", telegram_id="222")  # ok


def test_global_pending_cap(db, enable_new_user_requests, monkeypatch):
    monkeypatch.setattr(
        "app.services.user_access_requests._pending_cap",
        lambda _db: 1,
    )
    submit_access_request(db, request_type="new_user", telegram_id="1")
    with pytest.raises(RequestsClosed):
        submit_access_request(db, request_type="new_user", telegram_id="2")


def test_ban_blocks_submit(db, enable_new_user_requests):
    db.add(TelegramRequestBan(telegram_id="333"))
    db.commit()
    with pytest.raises(Banned):
        submit_access_request(db, request_type="new_user", telegram_id="333")


def test_add_config_requires_bound_user(db, enable_new_user_requests, bound_user):
    with pytest.raises(NotBound):
        submit_access_request(db, request_type="add_config", telegram_id="999")
    submit_access_request(
        db,
        request_type="add_config",
        telegram_id=bound_user.telegram_id,
        user_id=bound_user.id,
    )


def test_submit_writes_request_row(db, enable_new_user_requests):
    req = submit_access_request(
        db,
        request_type="new_user",
        telegram_id="777",
        telegram_username="ivan_user",
        telegram_name="Ivan User",
        user_note="прошу доступ",
    )
    assert req.id is not None
    assert req.status == "pending"
    assert req.telegram_id == "777"
    assert req.telegram_username == "ivan_user"


def test_extend_requires_bound_user(db, enable_new_user_requests):
    with pytest.raises(NotBound):
        submit_access_request(db, request_type="extend_access", telegram_id="999")
