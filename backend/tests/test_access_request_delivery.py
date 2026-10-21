"""Stage 2 Task 9: approval → delivery (D12).

TDD: ожидаем FAIL до реализации, затем PASS.
Покрытие: создание пользователя+портал+очередь provision, единое сообщение
requester'у только в личный чат, идемпотентность, отсутствие сообщения при 0 конфигов.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, User, UserAccessRequest, UserRole
from app.services.app_setting_store import _set_setting
from app.services.client_portal import _active_user_token
from app.services.user_access_requests import (
    deliver_approved_request,
    maybe_send_delivery_after_task,
    send_message_sync_or_async,
    user_link_response,
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
def admin(db):
    user = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def user(db):
    user = User(
        username="ivan_user",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        telegram_id="777",
        panel_login_enabled=False,
        can_create_configs=False,
        client_base_name="ivan_user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def approved_request(db, user):
    req = UserAccessRequest(
        request_type="new_user",
        user_id=user.id,
        telegram_id="777",
        telegram_name="Ivan",
        status="approved",
        reviewed_by_id=None,
        reviewed_at=None,
        delivered_at=None,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def _no_enqueue(db, **_kw):
    return SimpleNamespace(id="t1")


def test_delivery_creates_user_portal_and_enqueues(
    db, approved_request, user, admin, monkeypatch
):
    enqueued = []
    monkeypatch.setattr(
        "app.services.user_access_requests.enqueue_user_provision",
        lambda db, **kw: enqueued.append(kw) or SimpleNamespace(id="t1"),
    )
    result_user, task = deliver_approved_request(
        db, request=approved_request, user=user, plan={}, actor=admin
    )
    assert result_user.panel_login_enabled is False
    assert result_user.can_create_configs is False
    assert result_user.telegram_id == approved_request.telegram_id
    assert _active_user_token(db, user_id=user.id) is not None
    assert task is not None
    assert enqueued and enqueued[0]["user_id"] == user.id


def test_delivery_message_sent_once_only_to_requester(
    db, approved_request, user, monkeypatch
):
    _set_setting(db, "telegram_bot_token", "TOKEN")
    db.commit()
    sent = []
    def _fake_send(token, chat_id, text, **k):
        sent.append((str(chat_id), text))
        return True

    monkeypatch.setattr(
        "app.services.user_access_requests.send_message_sync_or_async",
        _fake_send,
    )
    monkeypatch.setattr(
        "app.services.user_access_requests.user_link_response",
        lambda db, row: {"url": "https://portal.example.com/p/u_abc123", "token": "u_abc123"},
    )
    maybe_send_delivery_after_task(db, user_id=user.id, created_count=2)
    assert len(sent) == 1
    assert sent[0][0] == user.telegram_id
    assert "Доступ одобрен" in sent[0][1]
    assert "/p/" in sent[0][1] or "u_" in sent[0][1]
    db.refresh(approved_request)
    assert approved_request.delivered_at is not None
    # Повтор — идемпотентно, сообщение не дублируется.
    maybe_send_delivery_after_task(db, user_id=user.id, created_count=2)
    assert len(sent) == 1


def test_delivery_message_carries_bound_reply_keyboard(db, approved_request, user, monkeypatch):
    """«Доступ одобрен» приходит с меню абонента, чтобы пропала кнопка «Запросить доступ»."""
    _set_setting(db, "telegram_bot_token", "TOKEN")
    db.commit()
    sent = []

    def _fake_send(token, chat_id, text, **kwargs):
        sent.append((str(chat_id), text, kwargs.get("reply_markup")))
        return True

    monkeypatch.setattr(
        "app.services.user_access_requests.send_message_sync_or_async", _fake_send
    )
    monkeypatch.setattr(
        "app.services.user_access_requests.user_link_response",
        lambda db, row: {"url": "https://portal.example.com/p/u_abc123", "token": "u_abc123"},
    )
    maybe_send_delivery_after_task(db, user_id=user.id, created_count=1)
    assert len(sent) == 1
    markup = sent[0][2] or {}
    buttons = [btn.get("text") for row in markup.get("keyboard", []) for btn in row]
    assert "Запросить ещё конфиг" in buttons
    assert "Запросить доступ" not in buttons


def test_no_requester_message_when_zero_configs(db, approved_request, user, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.user_access_requests.send_message_sync_or_async",
        lambda *a, **k: sent.append(1) or True,
    )
    maybe_send_delivery_after_task(db, user_id=user.id, created_count=0)
    assert sent == []
    # Админ получает колокол о неудачной доставке.
    from app.models import AdminPanelNotification

    rows = db.query(AdminPanelNotification).filter(
        AdminPanelNotification.event_type == "access_request_delivery_failed"
    ).all()
    assert len(rows) == 1


def test_delivery_not_marked_when_telegram_send_fails(db, approved_request, user, monkeypatch):
    _set_setting(db, "telegram_bot_token", "TOKEN")
    db.commit()
    monkeypatch.setattr(
        "app.services.user_access_requests.send_message_sync_or_async",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "app.services.user_access_requests.user_link_response",
        lambda db, row: {"url": "https://portal.example.com/p/u_abc123", "token": "u_abc123"},
    )
    maybe_send_delivery_after_task(db, user_id=user.id, created_count=2)
    db.refresh(approved_request)
    assert approved_request.delivered_at is None
    from app.models import AdminPanelNotification

    rows = db.query(AdminPanelNotification).filter(
        AdminPanelNotification.event_type == "access_request_delivery_failed"
    ).all()
    assert len(rows) == 1
