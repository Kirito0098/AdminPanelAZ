"""Stage 2 Task 4: notifications SSE stream + stream ticket с именем `notifications`."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import anyio
import pytest
from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.database import Base
from app.models import User, UserRole
from app.routers import notifications as notifications_mod
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


def _run_async(func):
    return anyio.run(func)


def _stream_request() -> Request:
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
        }
    )
    request.is_disconnected = lambda: asyncio.sleep(0, result=False)
    return request


async def _first_data_payload(ticket: str) -> dict:
    response = await notifications_mod.notifications_stream(_stream_request(), ticket=ticket)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, (bytes, bytearray)) else chunk
        for line in text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[len("data: ") :])
    raise AssertionError("SSE stream did not emit a data event")


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


def test_stream_endpoint_emits_update_on_change(db, admin, monkeypatch):
    # Stream auth/ticks open+close their own sessions — do not reuse the fixture
    # session (it would be closed mid-test). Avoid httpx ASGITransport SSE deadlock
    # by driving StreamingResponse.body_iterator directly.
    StreamSession = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr(notifications_mod, "_db_session_factory", StreamSession)
    monkeypatch.setattr(notifications_mod, "SessionLocal", StreamSession)
    monkeypatch.setattr(notifications_mod, "_POLL_INTERVAL_SECONDS", 0.05)

    async def run_sync(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(notifications_mod.asyncio, "to_thread", run_sync)

    ticket_user = SimpleNamespace(id=admin.id, token_version=admin.token_version or 0)
    ticket = issue_stream_ticket(ticket_user, "notifications")
    db.commit()
    db.close()

    async def main():
        first = await _first_data_payload(ticket)
        assert first["max_notification_id"] == 0

        with StreamSession() as write_db:
            write_admin_panel_notification(write_db, event_type="node_offline", title="новое")

        second = await _first_data_payload(issue_stream_ticket(ticket_user, "notifications"))
        assert second["max_notification_id"] == 1

    _run_async(main)


def test_stream_endpoint_rejects_unknown_ticket(db, admin, monkeypatch):
    StreamSession = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr(notifications_mod, "_db_session_factory", StreamSession)
    monkeypatch.setattr(notifications_mod, "SessionLocal", StreamSession)
    db.commit()
    db.close()

    async def main():
        with pytest.raises(HTTPException) as exc:
            await notifications_mod.notifications_stream(_stream_request(), ticket="unknown")
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED

    _run_async(main)
