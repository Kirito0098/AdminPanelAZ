"""PATCH /users/{id}: админские поля закрыты для обычного пользователя, свои — работают."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import users as users_router

ADMIN_ONLY_PAYLOADS = [
    ("лимит трафика", {"traffic_limit_bytes": 100}),
    ("роль", {"role": "admin"}),
    ("статус", {"is_active": False}),
    ("вход в панель", {"panel_login_enabled": False}),
    ("срок доступа", {"access_until": "2030-01-01"}),
    ("квота", {"config_quota": 5}),
    ("право создания конфигов", {"can_create_configs": True}),
    ("право управления конфигами", {"can_manage_configs": True}),
    ("видимость VPN-профилей", {"visible_vpn_profiles": None}),
    ("заметка", {"note": "x"}),
    ("Telegram ID", {"telegram_id": "999"}),
]


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


@pytest.fixture()
def client(db):
    user = User(
        username="plain",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        panel_login_enabled=True,
        provision_state="unmanaged",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), user


@pytest.mark.parametrize("label,payload", ADMIN_ONLY_PAYLOADS, ids=[p[0] for p in ADMIN_ONLY_PAYLOADS])
def test_non_admin_cannot_change_admin_only_fields(client, label, payload) -> None:
    api, user = client
    response = api.patch(f"/api/users/{user.id}", json=payload)
    assert response.status_code == 403, (label, response.status_code, response.text)
    assert "Только администратор" in response.json()["detail"]


def test_non_admin_can_update_own_non_admin_field(client) -> None:
    api, user = client
    response = api.patch(f"/api/users/{user.id}", json={"theme": "dark"})
    assert response.status_code == 200, response.text
    assert response.json()["theme"] == "dark"


def test_non_admin_can_unlink_own_telegram(client) -> None:
    api, user = client
    response = api.patch(f"/api/users/{user.id}", json={"telegram_id": ""})
    assert response.status_code == 200, response.text
    assert response.json()["telegram_id"] is None
