"""One-time stream tickets replace access tokens in SSE/WebSocket query strings."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user_access_token
from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import awg2, monitoring, session as session_router, warper
from app.services import shared_state
from app.services.stream_ticket import (
    STREAM_TICKET_TTL,
    admin_from_stream_ticket,
    issue_stream_ticket,
    redeem_stream_ticket,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all(
        [
            User(id=1, username="admin", password_hash="x", role=UserRole.admin, is_active=True),
            User(id=2, username="alice", password_hash="x", role=UserRole.user, is_active=True),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_ticket_is_single_use(db):
    ticket = issue_stream_ticket(db.get(User, 1), "monitoring")

    assert redeem_stream_ticket(db, ticket, "monitoring").username == "admin"
    assert redeem_stream_ticket(db, ticket, "monitoring") is None


def test_ticket_is_bound_to_its_stream(db):
    ticket = issue_stream_ticket(db.get(User, 1), "monitoring")

    assert redeem_stream_ticket(db, ticket, "awg2_install") is None
    assert redeem_stream_ticket(db, ticket, "monitoring") is None


def test_ticket_expires(db, monkeypatch):
    ticket = issue_stream_ticket(db.get(User, 1), "warper_update")
    later = shared_state._now() + STREAM_TICKET_TTL + timedelta(seconds=1)
    monkeypatch.setattr(shared_state, "_now", lambda: later)

    assert redeem_stream_ticket(db, ticket, "warper_update") is None


def test_ticket_dies_with_session_invalidation(db):
    admin = db.get(User, 1)
    ticket = issue_stream_ticket(admin, "server_monitor")
    admin.token_version = (admin.token_version or 0) + 1
    db.commit()

    assert redeem_stream_ticket(db, ticket, "server_monitor") is None


def test_ticket_of_disabled_user_is_rejected(db):
    admin = db.get(User, 1)
    ticket = issue_stream_ticket(admin, "monitoring")
    admin.is_active = False
    db.commit()

    assert redeem_stream_ticket(db, ticket, "monitoring") is None


def test_admin_from_stream_ticket_errors(db):
    with pytest.raises(HTTPException) as exc:
        admin_from_stream_ticket(db, "", "monitoring")
    assert exc.value.status_code == 401

    ticket = issue_stream_ticket(db.get(User, 2), "monitoring")
    with pytest.raises(HTTPException) as exc:
        admin_from_stream_ticket(db, ticket, "monitoring")
    assert exc.value.status_code == 403


def test_stream_ticket_endpoint_is_admin_only(db):
    app = FastAPI()
    app.include_router(session_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    admin_auth = {"Authorization": f"Bearer {create_user_access_token(db.get(User, 1))}"}
    user_auth = {"Authorization": f"Bearer {create_user_access_token(db.get(User, 2))}"}

    ok = client.post("/api/stream-ticket", json={"stream": "monitoring"}, headers=admin_auth)
    assert ok.status_code == 200
    assert ok.json()["expires_in_seconds"] == 30
    assert redeem_stream_ticket(db, ok.json()["ticket"], "monitoring").username == "admin"

    assert client.post("/api/stream-ticket", json={"stream": "monitoring"}, headers=user_auth).status_code == 403
    assert client.post("/api/stream-ticket", json={"stream": "files"}, headers=admin_auth).status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/monitoring/stream",
        "/api/warper/updates/stream",
        "/api/awg2/install/stream?mode=install",
    ],
)
def test_streams_no_longer_accept_token_query(path):
    app = FastAPI()
    for router in (monitoring.router, warper.router, awg2.router):
        app.include_router(router, prefix="/api")
    separator = "&" if "?" in path else "?"

    response = TestClient(app).get(f"{path}{separator}token=jwt")

    assert response.status_code == 422
