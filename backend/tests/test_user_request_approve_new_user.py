"""Одобрение заявки new_user: имена абонента не должны ронять одобрение.

Регрессия: логин абонента «в удалении» считался свободным (``_login_is_free``
исключал ``pending_deletion``), а уникальный индекс ``uq_users_client_base_name_lower``
такого исключения не делает — вставка падала с ``IntegrityError`` (500), заявка
оставалась ``approved`` без абонента (``user_id = NULL``), и одобрить её снова
было нельзя.
"""

import pytest
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


def test_taken_login_is_a_clear_error_not_500(db):
    node = _node(db)
    _leftover_user(db, name="TopTinker2")
    request = _request(db)

    with pytest.raises(ValueError, match="Логин .* уже занят"):
        _approve(db, request, node=node, username="TopTinker2")

    db.refresh(request)
    assert request.status == "pending"
    assert db.query(User).filter(User.username == "TopTinker2").count() == 1


def test_taken_base_name_is_a_clear_error_not_500(db):
    node = _node(db)
    leftover = _leftover_user(db, name="other")
    leftover.client_base_name = "TopTinker2"
    db.add(leftover)
    db.commit()
    request = _request(db)

    with pytest.raises(ValueError, match="Имя конфигов .* уже занято"):
        _approve(db, request, node=node, username="TopTinker2")

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
