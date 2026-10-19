"""Stage 2 Task 4: notifications SSE stream + stream ticket с именем `notifications`."""

from __future__ import annotations

import json

import anyio
import pytest
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user_access_token
from app.database import Base, get_db
from app.models import AdminPanelNotification, User, UserRole
from app.routers.notifications import _db_session_factory, router as notifications_router
from app.services.admin_panel_notifications import notifications_stream_snapshot, write_admin_panel_notification
from app.services.stream_ticket import admin_from_stream_ticket, issue_stream_ticket


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


def _make_app(db):
    app = FastAPI()
    app.include_router(notifications_router, prefix="/api")

    def _get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    return app


def _run_async(func):
    return anyio.run(func)


# ---------- ticket ----------


def test_notifications_stream_rejects_wrong_ticket_stream(db, admin):
    ticket = issue_stream_ticket(admin, "monitoring")
    with pytest.raises(HTTPException) as exc:
        admin_from_stream_ticket(db, ticket, "notifications")
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_notifications_ticket_is_single_use_and_stream_bound(db, admin):
    ticket = issue_stream_ticket(admin, "notifications")
    user = admin_from_stream_ticket(db, ticket, "notifications")
    assert user.id == admin.id

    with pytest.raises(HTTPException) as exc:
        admin_from_stream_ticket(db, ticket, "notifications")
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED

    other_ticket = issue_stream_ticket(admin, "monitoring")
    with pytest.raises(HTTPException) as exc:
        admin_from_stream_ticket(db, other_ticket, "notifications")
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


# ---------- snapshot ----------


def test_poll_snapshot_changes_when_max_id_grows(db, admin):
    s1 = notifications_stream_snapshot(db)
    assert s1["max_notification_id"] == 0
    assert s1["pending_request_ids"] == []
    assert s1["tasks"] == []

    write_admin_panel_notification(db, event_type="node_offline", title="появилось")
    s2 = notifications_stream_snapshot(db)
    assert s2["max_notification_id"] == s1["max_notification_id"] + 1


# ---------- SSE endpoint ----------


async def _first_data_event(client, ticket):
    async with client.stream(
        "GET", "/api/notifications/stream", params={"ticket": ticket}
    ) as response:
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"

        async for line in response.aiter_lines():
            if line.startswith("data: "):
                return json.loads(line[len("data: "):])
        raise AssertionError("SSE stream did not emit a data event")


def test_stream_endpoint_emits_update_on_change(db, admin, monkeypatch):
    monkeypatch.setattr("app.routers.notifications._db_session_factory", lambda: db)

    ticket = issue_stream_ticket(admin, "notifications")
    app = _make_app(db)

    async def main():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Первый тик всегда шлёт текущий снимок.
            first = await _first_data_event(client, ticket)
            assert first["max_notification_id"] == 0

            write_admin_panel_notification(db, event_type="node_offline", title="новое")

            # Новый поток с новым билетом — снимок уже с ростом max id.
            second = await _first_data_event(
                client, issue_stream_ticket(admin, "notifications")
            )
            assert second["max_notification_id"] == 1

    _run_async(main)


def test_stream_endpoint_rejects_unknown_ticket(db, admin, monkeypatch):
    monkeypatch.setattr("app.routers.notifications._db_session_factory", lambda: db)
    app = _make_app(db)

    async def main():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream(
                "GET", "/api/notifications/stream", params={"ticket": "unknown"}
            ) as response:
                assert response.status_code == status.HTTP_401_UNAUTHORIZED

    _run_async(main)
