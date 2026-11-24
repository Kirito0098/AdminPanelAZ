"""Одобрение заявки new_user: имена абонента не должны ронять одобрение.

Регрессия: логин абонента «в удалении» считался свободным (``_login_is_free``
исключал ``pending_deletion``), а уникальный индекс ``uq_users_client_base_name_lower``
такого исключения не делает — вставка падала с ``IntegrityError`` (500), заявка
оставалась ``approved`` без абонента (``user_id = NULL``), и одобрить её снова
было нельзя.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, User, UserAccessRequest, UserRole
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


@pytest.fixture(autouse=True)
def _no_delivery(monkeypatch):
    # Доставка портала и сообщение в Telegram — не предмет этих тестов.
    monkeypatch.setattr(uar, "deliver_approved_request", lambda *a, **k: (None, None))


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


def _node(db) -> Node:
    node = Node(name="nl-1", host="10.0.0.1", node_kind="vpn")
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _leftover_user(db, *, name: str) -> User:
    """Абонент, которого удаляют: имя всё ещё занимает уникальные индексы."""
    user = User(
        username=name,
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        panel_login_enabled=False,
        client_base_name=name,
        provision_state="pending_deletion",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _request(db, *, telegram_id: str = "777", telegram_username: str | None = None):
    row = UserAccessRequest(
        request_type=uar.REQUEST_TYPE_NEW_USER,
        telegram_id=telegram_id,
        telegram_username=telegram_username,
        telegram_name="Иван",
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _approve(db, request, *, node: Node, username: str | None = None) -> UserAccessRequest:
    return uar.approve_request(
        db,
        request_id=request.id,
        admin=_admin(db),
        ad_hoc={
            "node_ids": [node.id],
            "protocols": ["openvpn"],
            "config_count": 1,
            "username": username,
        },
    )


def test_taken_login_of_deleting_user_explains_the_wait(db):
    """Имя держит абонент «на удаление» — просим подождать, а не просто «занято»."""
    node = _node(db)
    _leftover_user(db, name="TopTinker2")
    request = _request(db)

    with pytest.raises(ValueError) as exc:
        _approve(db, request, node=node, username="TopTinker2")

    message = str(exc.value)
    assert "ещё занят" in message
    assert "TopTinker2" in message and "удаляется" in message
    db.refresh(request)
    assert request.status == "pending"
    assert db.query(User).filter(User.username == "TopTinker2").count() == 1


def test_taken_login_of_active_user_asks_for_another_name(db):
    node = _node(db)
    active = User(
        username="busy",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        panel_login_enabled=True,
        client_base_name="busy",
        provision_state="ok",
    )
    db.add(active)
    db.commit()
    request = _request(db)

    with pytest.raises(ValueError) as exc:
        _approve(db, request, node=node, username="busy")

    assert "уже занят абонентом busy" in str(exc.value)
    db.refresh(request)
    assert request.status == "pending"


def test_taken_base_name_is_a_clear_error_not_500(db):
    """Логин свободен, но имя конфигов держит удаляемый абонент — тоже понятная ошибка."""
    node = _node(db)
    leftover = _leftover_user(db, name="other")
    leftover.client_base_name = "TopTinker2"
    db.add(leftover)
    db.commit()
    request = _request(db)

    with pytest.raises(ValueError) as exc:
        _approve(db, request, node=node, username="TopTinker2")

    message = str(exc.value)
    assert "Имя конфигов" in message and "удаляется" in message
    db.refresh(request)
    assert request.status == "pending"


def test_failed_creation_reopens_request(db, monkeypatch):
    node = _node(db)
    request = _request(db)

    def _boom(*_a, **_k):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(uar, "_create_user_for_request", _boom)

    with pytest.raises(RuntimeError):
        _approve(db, request, node=node)

    db.refresh(request)
    assert request.status == "pending"
    assert request.reviewed_at is None
    assert request.user_id is None


def test_auto_login_skips_name_held_by_deleted_user(db):
    node = _node(db)
    _leftover_user(db, name="top")
    request = _request(db, telegram_id="777", telegram_username="top")

    decided = _approve(db, request, node=node)

    created = db.query(User).filter(User.telegram_id == "777").one()
    assert created.username == "tg777"
    assert created.client_base_name == "tg777"
    assert decided.status == "approved"
    assert decided.user_id == created.id


def test_approve_new_user_with_config_ids_keeps_them(db, monkeypatch):
    """Fider #47: роутер терял config_ids, и «без новых конфигов» падало с 400.

    Проверяется именно проброс: сервис умеет привязку готовых конфигов, но
    в ``ad_hoc`` для new_user уходили только узлы и протоколы, поэтому заявка
    отклонялась с «Укажите узлы и протоколы плана».
    """
    from app.routers import users as users_router
    from app.schemas import ApproveRequest

    request_row = _request(db)
    captured: dict = {}

    def _fake_approve(_db, **kwargs):
        captured.update(kwargs)
        return request_row

    monkeypatch.setattr(users_router, "_require_provisioning", lambda: None)
    monkeypatch.setattr(users_router, "approve_request", _fake_approve)
    monkeypatch.setattr(users_router, "_sync_request_messages_after_decide", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.telegram_widgets.refresh_access_request_cards_sync", lambda *a, **k: None
    )
    monkeypatch.setattr(users_router.settings, "audit_log_enabled", False)

    response = users_router.approve_access_request(
        request_id=request_row.id,
        payload=ApproveRequest(config_ids=[11, 12], username="ivan"),
        request=MagicMock(),
        db=db,
        admin=_admin(db),
    )

    assert captured["ad_hoc"]["config_ids"] == [11, 12]
    assert captured["ad_hoc"]["username"] == "ivan"
    assert response.id == request_row.id


def test_approve_new_user_with_empty_config_ids_explains_what_to_do(db, monkeypatch):
    """Режим «без новых конфигов» без выбранных конфигов — внятная 400, а не про узлы."""
    from app.routers import users as users_router
    from app.schemas import ApproveRequest

    request_row = _request(db)
    monkeypatch.setattr(users_router, "_require_provisioning", lambda: None)

    def _unexpected(*_a, **_k):
        raise AssertionError("approve_request не должен вызываться")

    monkeypatch.setattr(users_router, "approve_request", _unexpected)

    with pytest.raises(HTTPException) as excinfo:
        users_router.approve_access_request(
            request_id=request_row.id,
            payload=ApproveRequest(config_ids=[]),
            request=MagicMock(),
            db=db,
            admin=_admin(db),
        )

    assert excinfo.value.status_code == 400
    assert "хотя бы один конфиг" in excinfo.value.detail
