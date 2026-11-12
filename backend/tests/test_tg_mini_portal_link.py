"""Mini App: абонент сам получает и перевыпускает ссылку клиентского портала."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_tg_mini_user
from app.database import Base, get_db
from app.models import User, UserPortalToken, UserRole
from app.routers.tg_mini import me_portal
from app.routers.tg_mini.me_portal import router as me_portal_router
from app.services import client_portal
from app.services.feature_guards import module_disabled_message


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


class _Features:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def is_enabled(self, key: str) -> bool:
        return self.enabled


@pytest.fixture(autouse=True)
def portal_ready(monkeypatch):
    monkeypatch.setattr(me_portal, "get_feature_service", lambda: _Features(True))
    monkeypatch.setattr(me_portal, "get_portal_link_ttl_days", lambda db: 30)
    monkeypatch.setattr(me_portal, "resolve_portal_base_url", lambda db: "https://portal.example")
    monkeypatch.setattr(
        client_portal, "resolve_portal_base_url", lambda db: "https://portal.example"
    )


@pytest.fixture()
def client(db):
    app = FastAPI()
    app.include_router(me_portal_router, prefix="/api/tg-mini")

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _user(db, username: str, telegram_id: str = "111") -> User:
    user = User(
        username=username,
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        panel_login_enabled=True,
        telegram_id=telegram_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_feature_disabled_blocks_portal_link(client, db, monkeypatch):
    monkeypatch.setattr(me_portal, "get_feature_service", lambda: _Features(False))
    user = _user(db, "ivan")
    client.app.dependency_overrides[get_tg_mini_user] = lambda: user

    response = client.get("/api/tg-mini/me/portal-link")

    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
    assert response.json()["detail"] == module_disabled_message("client_portal")


def test_user_creates_and_reuses_own_link(client, db):
    user = _user(db, "ivan")
    client.app.dependency_overrides[get_tg_mini_user] = lambda: user

    empty = client.get("/api/tg-mini/me/portal-link")
    assert empty.status_code == status.HTTP_200_OK, empty.text
    assert empty.json()["exists"] is False

    created = client.post("/api/tg-mini/me/portal-link")
    assert created.status_code == status.HTTP_200_OK, created.text
    body = created.json()
    assert body["exists"] is True
    assert body["url"].startswith("https://portal.example/p/")
    assert body["ttl_days"] == 30
    assert body["expired"] is False

    again = client.post("/api/tg-mini/me/portal-link")
    assert again.json()["url"] == body["url"]


def test_links_of_two_users_differ(client, db):
    ivan = _user(db, "ivan", telegram_id="111")
    petr = _user(db, "petr", telegram_id="222")

    client.app.dependency_overrides[get_tg_mini_user] = lambda: ivan
    ivan_url = client.post("/api/tg-mini/me/portal-link").json()["url"]
    client.app.dependency_overrides[get_tg_mini_user] = lambda: petr
    petr_url = client.post("/api/tg-mini/me/portal-link").json()["url"]

    assert ivan_url != petr_url


def test_expired_link_is_rotated_on_request(client, db):
    user = _user(db, "ivan")
    old = UserPortalToken(
        token="old-token",
        user_id=user.id,
        created_at=datetime.utcnow() - timedelta(days=40),
    )
    db.add(old)
    db.commit()
    client.app.dependency_overrides[get_tg_mini_user] = lambda: user

    expired = client.get("/api/tg-mini/me/portal-link")
    assert expired.json()["expired"] is True

    renewed = client.post("/api/tg-mini/me/portal-link").json()
    assert renewed["expired"] is False
    assert renewed["url"] != "https://portal.example/p/old-token"


def test_portal_not_ready_is_explained(client, db, monkeypatch):
    monkeypatch.setattr(me_portal, "resolve_portal_base_url", lambda db: None)
    user = _user(db, "ivan")
    client.app.dependency_overrides[get_tg_mini_user] = lambda: user

    response = client.get("/api/tg-mini/me/portal-link")

    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text
