"""Stage 2 Task 8: approve/reject API + race + Telegram-bound check + archive.

TDD: ожидаем FAIL до реализации, затем PASS.
Покрытие: двойное одобрение → 409 AlreadyDecided, отказ при привязанном TG,
архив при удалении пользователя.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    Base,
    Node,
    NodeStatus,
    TelegramRequestBan,
    TelegramUserArchive,
    User,
    UserAccessRequest,
    UserRole,
)
from app.routers.users import delete_user as delete_user_route
from app.services.user_access_requests import (
    AlreadyDecided,
    TelegramAlreadyBound,
    approve_request,
    reject_request,
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
def node(db):
    node = Node(
        name="n1",
        host="127.0.0.1",
        port=9100,
        api_key_hash="h",
        api_key_encrypted="e",
        status=NodeStatus.online,
        is_local=True,
        node_kind="vpn",
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@pytest.fixture()
def default_preset(db, node):
    from app.services.provisioning_presets import create_preset

    return create_preset(
        db,
        name="trial-3d",
        node_ids=[node.id],
        protocols=["wireguard"],
        config_count=1,
        access_days=3,
        is_default=True,
    )


@pytest.fixture()
def pending_new_user_request(db):
    req = UserAccessRequest(
        request_type="new_user",
        telegram_id="111",
        telegram_username="ivan_user",
        telegram_name="Ivan",
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def _no_enqueue(db, **_kw):
    return SimpleNamespace(id="t1")


def test_double_approve_race_second_gets_409(
    db, pending_new_user_request, admin, node, default_preset, monkeypatch
):
    monkeypatch.setattr(
        "app.services.user_access_requests.enqueue_user_provision", _no_enqueue
    )
    ok1 = approve_request(
        db, request_id=pending_new_user_request.id, admin=admin, preset_id=default_preset.id
    )
    assert ok1.status == "approved"
    with pytest.raises(AlreadyDecided):
        approve_request(
            db, request_id=pending_new_user_request.id, admin=admin, preset_id=default_preset.id
        )


def test_approve_refuses_when_telegram_bound_elsewhere(
    db, pending_new_user_request, admin, node, default_preset, monkeypatch
):
    monkeypatch.setattr(
        "app.services.user_access_requests.enqueue_user_provision", _no_enqueue
    )
    other = User(username="ivan", password_hash="x", role=UserRole.user, telegram_id="111")
    db.add(other)
    db.commit()
    with pytest.raises(TelegramAlreadyBound) as ei:
        approve_request(
            db,
            request_id=pending_new_user_request.id,
            admin=admin,
            ad_hoc={
                "node_ids": [node.id],
                "protocols": ["wireguard"],
                "config_count": 1,
            },
        )
    assert "уже привязан" in str(ei.value.admin_detail)
    assert "ivan" in str(ei.value.admin_detail)
    # Заявка осталась pending (одобрение не прошло).
    db.refresh(pending_new_user_request)
    assert pending_new_user_request.status == "pending"


def test_approve_new_user_creates_bound_user(
    db, pending_new_user_request, admin, node, default_preset, monkeypatch
):
    monkeypatch.setattr(
        "app.services.user_access_requests.enqueue_user_provision", _no_enqueue
    )
    decided = approve_request(
        db,
        request_id=pending_new_user_request.id,
        admin=admin,
        preset_id=default_preset.id,
    )
    assert decided.status == "approved"
    assert decided.reviewed_by_id == admin.id
    user = db.query(User).filter(User.telegram_id == "111").one()
    assert decided.user_id == user.id  # delivery lookup after provision
    assert user.panel_login_enabled is False
    assert user.can_create_configs is False
    assert user.client_base_name == "ivan_user"


def test_reject_request(db, pending_new_user_request, admin):
    decided = reject_request(
        db, request_id=pending_new_user_request.id, admin=admin, reason="не подходит", ban=True
    )
    assert decided.status == "rejected"
    assert decided.reject_reason == "не подходит"
    ban = db.query(TelegramRequestBan).filter_by(telegram_id="111").one()
    assert ban.telegram_id == "111"


def test_delete_user_writes_telegram_archive(db, admin):
    user = User(
        username="ivan",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        telegram_id="444",
        access_until=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Вызываем логику удаления через роутер (запись архива внутри).
    from fastapi import HTTPException

    class FakeRequest:
        client = None
        headers = {}

    response = delete_user_route(
        user_id=user.id,
        request=FakeRequest(),
        db=db,
        current_user=admin,
    )
    # Не зависло и удалило пользователя.
    assert db.get(User, user.id) is None
    row = (
        db.query(TelegramUserArchive)
        .filter_by(telegram_id="444", username="ivan")
        .one()
    )
    assert row.username == "ivan"
    assert row.last_access_until is None
