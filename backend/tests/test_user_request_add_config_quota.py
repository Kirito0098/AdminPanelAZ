"""Одобрение «ещё один конфиг»: план и «лимит имён» растут вместе.

Регрессия: раньше одобрение заявки ``add_config`` расширяло только план,
карточка показывала ``3 / 2``, самосервис блокировался, а в Telegram
приходило «Доступ одобрен» вместо «Дополнительный конфиг одобрен».
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserAccessRequest, UserRole
from app.services import user_access_requests as uar


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _admin(db) -> User:
    user = User(
        username="admin",
        password_hash="x",
        role=UserRole.admin,
        is_active=True,
        panel_login_enabled=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _subscriber(db, *, indexes: list[int], quota: int | None) -> User:
    user = User(
        username="ivan",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        panel_login_enabled=True,
        client_base_name="ivan",
        plan_config_indexes=json.dumps(indexes),
        desired_protocols=json.dumps(["wireguard"]),
        config_quota=quota,
        telegram_id="111",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _request(db, user: User) -> UserAccessRequest:
    row = UserAccessRequest(
        request_type=uar.REQUEST_TYPE_ADD_CONFIG,
        user_id=user.id,
        telegram_id="111",
        requested_count=1,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _approve(db, monkeypatch, request: UserAccessRequest) -> None:
    admin = _admin(db)
    # Оформление портала и provision-задача — не предмет этого теста.
    monkeypatch.setattr(uar, "deliver_approved_request", lambda *a, **k: (None, None))
    uar.approve_request(db, request_id=request.id, admin=admin, ad_hoc={"count": 1})


def test_add_config_approval_grows_quota_with_plan(db, monkeypatch):
    user = _subscriber(db, indexes=[1, 2], quota=2)
    request = _request(db, user)

    _approve(db, monkeypatch, request)

    db.refresh(user)
    assert json.loads(user.plan_config_indexes) == [1, 2, 3]
    assert user.config_quota == 3


def test_add_config_approval_keeps_panel_default_quota(db, monkeypatch):
    user = _subscriber(db, indexes=[1], quota=0)
    request = _request(db, user)

    _approve(db, monkeypatch, request)

    db.refresh(user)
    assert json.loads(user.plan_config_indexes) == [1, 2]
    assert user.config_quota == 0


def test_add_config_delivery_text_differs_from_access():
    text = uar._delivery_text("https://panel.test/u/token", None, added=True)

    assert text.splitlines()[0] == "✅ Дополнительный конфиг одобрен"
    assert "Доступ одобрен" not in text
