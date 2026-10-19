"""Stage 2 Task 3: notifications REST API — unread arithmetic per admin + mark read.

TDD: ожидаем FAIL до реализации роутера и хелперов, затем PASS.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user_access_token
from app.database import Base, get_db
from app.models import AdminPanelNotification, User, UserAccessRequest, UserRole
from app.routers.notifications import router as notifications_router
from app.services.admin_panel_notifications import (
    list_notifications_for_admin,
    mark_notifications_read,
    write_admin_panel_notification,
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
def client(db, admin, monkeypatch):
    monkeypatch.setattr(
        "app.routers.notifications.get_feature_service",
        lambda: MagicMock(is_enabled=lambda _k: False),
    )

    app = FastAPI()
    app.include_router(notifications_router, prefix="/api")

    def _get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _headers(user):
    return {"Authorization": f"Bearer {create_user_access_token(user)}"}


def _seed(db, *, count=3, event_type="node_offline"):
    ids = []
    for i in range(count):
        row = write_admin_panel_notification(
            db,
            event_type=event_type,
            title=f"Событие {i}",
            message=f"Сообщение {i}",
        )
        ids.append(row.id)
    return ids


# ---------- helpers ----------


def test_list_notifications_for_admin_unread_count(db, admin):
    _seed(db, count=3)
    admin.last_read_notification_id = 1
    db.commit()

    items, unread = list_notifications_for_admin(db, admin)
    assert len(items) == 3
    assert unread == 2  # id 2 и 3 больше last_read=1

    items, unread = list_notifications_for_admin(db, admin, limit=1)
    assert len(items) == 1
    assert items[0]["id"] == 3  # порядок id DESC


def test_list_notifications_for_admin_category(db, admin):
    write_admin_panel_notification(db, event_type="node_offline", title="n1")
    write_admin_panel_notification(db, event_type="cidr_deploy_failed", title="s1")

    items, unread = list_notifications_for_admin(db, admin, category="services")
    assert len(items) == 1
    assert items[0]["category"] == "services"
    assert items[0]["title"] == "s1"


def test_mark_notifications_read_max(db, admin):
    _seed(db, count=3)

    mark_notifications_read(db, admin, 2)
    assert admin.last_read_notification_id == 2

    mark_notifications_read(db, admin, 1)  # уже было больше — не откатываем
    assert admin.last_read_notification_id == 2


# ---------- API ----------


def test_unread_is_per_admin(client, db, admin):
    other = User(username="admin_b", password_hash="x", role=UserRole.admin, is_active=True)
    db.add(other)
    db.commit()
    db.refresh(other)

    _seed(db, count=3)

    r = client.get("/api/notifications", headers=_headers(admin))
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["unread_count"] == 3
    assert len(r.json()["items"]) == 3

    top = db.query(func.max(AdminPanelNotification.id)).scalar()
    r = client.post(
        "/api/notifications/read", json={"up_to_id": top}, headers=_headers(admin)
    )
    assert r.status_code == status.HTTP_200_OK

    r = client.get("/api/notifications", headers=_headers(admin))
    assert r.json()["unread_count"] == 0

    # у другого админа собственная арифметика прочитанного
    r = client.get("/api/notifications", headers=_headers(other))
    assert r.json()["unread_count"] == 3


def test_mark_read_persists_and_clamps(client, db, admin):
    _seed(db, count=3)
    admin.last_read_notification_id = 100
    db.commit()

    r = client.post(
        "/api/notifications/read", json={"up_to_id": 5}, headers=_headers(admin)
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.json() == {"ok": True}

    db.refresh(admin)
    assert admin.last_read_notification_id == 100

    r = client.get("/api/notifications", headers=_headers(admin))
    assert r.json()["unread_count"] == 0


def test_mark_read_validation(client, admin):
    r = client.post(
        "/api/notifications/read", json={"up_to_id": 0}, headers=_headers(admin)
    )
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_category_filter_and_before_id(client, db, admin):
    write_admin_panel_notification(db, event_type="node_offline", title="n1")
    write_admin_panel_notification(db, event_type="cidr_deploy_failed", title="s1")
    write_admin_panel_notification(db, event_type="login_failed", title="s2")

    r = client.get(
        "/api/notifications",
        params={"category": "services", "limit": 1},
        headers=_headers(admin),
    )
    assert r.status_code == status.HTTP_200_OK
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["category"] == "services"
    last_id = body["items"][0]["id"]

    r = client.get(
        "/api/notifications", params={"before_id": last_id}, headers=_headers(admin)
    )
    assert all(item["id"] < last_id for item in r.json()["items"])


def test_pending_requests_count_only_when_feature_enabled(client, db, admin, monkeypatch):
    db.add(
        UserAccessRequest(
            telegram_id="111", request_type="new_user", status="pending", user_note="hi"
        )
    )
    db.commit()

    r = client.get("/api/notifications", headers=_headers(admin))
    assert r.json()["pending_requests_count"] == 0

    monkeypatch.setattr(
        "app.routers.notifications.get_feature_service",
        lambda: MagicMock(is_enabled=lambda k: k == "user_provisioning"),
    )
    r = client.get("/api/notifications", headers=_headers(admin))
    assert r.json()["pending_requests_count"] == 1


def test_non_admin_rejected(client, db):
    user = User(username="user", password_hash="x", role=UserRole.user, is_active=True)
    db.add(user)
    db.commit()
    headers = {"Authorization": f"Bearer {create_user_access_token(user)}"}

    assert client.get("/api/notifications", headers=headers).status_code == 403
    assert client.post("/api/notifications/read", json={"up_to_id": 1}, headers=headers).status_code == 403
