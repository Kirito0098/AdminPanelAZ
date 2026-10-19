"""Stage 4 Task 7: баннер портала — запасной канал для пользователей без Telegram.

TDD: баннер сохраняется в карточке пользователя, показывается в meta портала
и исчезает после явного закрытия.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import User, UserPortalToken, UserRole
from app.routers import public_portal as public_portal_router
from app.services.bulk_user_nodes_notify import clear_portal_banner, set_portal_banner
from app.services.client_portal import build_user_portal_payload


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
    row = User(
        username="ivan",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        telegram_id=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def portal_token(db, user):
    row = UserPortalToken(token="ptok", user_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def client(db, monkeypatch):
    app = FastAPI()
    app.include_router(public_portal_router.router, prefix="/api")

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    monkeypatch.setattr("app.routers.public_portal.assert_portal_host", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.routers.public_portal.ip_restriction_service.get_client_ip",
        lambda *a, **k: "203.0.113.7",
    )
    monkeypatch.setattr(
        "app.routers.public_portal.public_download_rate_limit_service.consume",
        lambda *a, **k: None,
    )
    return TestClient(app)


@pytest.fixture()
def portal_base(monkeypatch):
    """Публикация портала настроена — иначе payload портала недоступен."""
    monkeypatch.setattr(
        "app.services.client_portal.resolve_portal_base_url",
        lambda db: "https://sub.example.com",
    )


def test_set_portal_banner_persists(db, user):
    set_portal_banner(db, user, "Сервер Germany отключён…")
    db.refresh(user)
    assert user.portal_banner_text.startswith("Сервер")
    assert user.portal_banner_at is not None


def test_clear_portal_banner_removes(db, user):
    set_portal_banner(db, user, "Текст")
    clear_portal_banner(db, user)
    db.refresh(user)
    assert user.portal_banner_text is None
    assert user.portal_banner_at is None


def test_meta_includes_banner(db, user, portal_token, portal_base):
    set_portal_banner(db, user, "Сервер Germany отключён…")
    db.refresh(user)
    payload = build_user_portal_payload(db, portal_token)
    assert payload["portal_banner"]["text"] == user.portal_banner_text
    assert payload["portal_banner"]["created_at"]


def test_meta_without_banner_has_none(db, user, portal_token, portal_base):
    payload = build_user_portal_payload(db, portal_token)
    assert payload["portal_banner"] is None


def test_dismiss_clears_banner(client, db, user, portal_token):
    set_portal_banner(db, user, "Сервер Germany отключён…")
    response = client.post(f"/api/public/portal/{portal_token.token}/banner/dismiss")
    assert response.status_code == 204
    db.refresh(user)
    assert user.portal_banner_text is None
    assert user.portal_banner_at is None
