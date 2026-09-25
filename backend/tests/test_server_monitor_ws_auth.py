"""/server-monitor/ws must accept only access tokens of active admins."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

import app.database as database_module
from app.auth import create_2fa_pending_token, create_access_token
from app.database import Base
from app.models import User, UserRole
from app.routers import server_monitor


@pytest.fixture
def ws_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all(
        [
            User(username="admin", password_hash="x", role=UserRole.admin, is_active=True),
            User(username="alice", password_hash="x", role=UserRole.user, is_active=True),
            User(username="retired", password_hash="x", role=UserRole.admin, is_active=False),
        ]
    )
    db.commit()
    db.close()

    adapter = MagicMock()
    adapter.get_server_metrics.return_value = {"cpu_percent": 1.0, "memory_percent": 2.0, "timestamp": "t"}
    adapter.get_server_live_throughput.return_value = {"interfaces": []}
    monkeypatch.setattr(database_module, "SessionLocal", factory)
    monkeypatch.setattr(server_monitor, "_is_server_monitor_enabled", lambda: True)
    monkeypatch.setattr(server_monitor, "get_active_adapter", lambda db: adapter)
    monkeypatch.setattr(server_monitor, "_WS_TICK_SLEEP_S", 0)

    app = FastAPI()
    app.include_router(server_monitor.router)
    yield TestClient(app)
    engine.dispose()


def _assert_rejected(client: TestClient, token: str) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/server-monitor/ws?token={token}") as ws:
            ws.receive_json()
    assert exc_info.value.code == 1008


def test_ws_rejects_2fa_pending_token(ws_client):
    _assert_rejected(ws_client, create_2fa_pending_token("admin"))


def test_ws_rejects_non_admin_user(ws_client):
    _assert_rejected(ws_client, create_access_token({"sub": "alice"}))


def test_ws_rejects_inactive_admin(ws_client):
    _assert_rejected(ws_client, create_access_token({"sub": "retired"}))


def test_ws_rejects_unknown_user(ws_client):
    _assert_rejected(ws_client, create_access_token({"sub": "ghost"}))


def test_ws_streams_metrics_for_active_admin(ws_client):
    token = create_access_token({"sub": "admin"})
    with ws_client.websocket_connect(f"/server-monitor/ws?token={token}") as ws:
        payload = ws.receive_json()

    assert payload["cpu_percent"] == 1.0
