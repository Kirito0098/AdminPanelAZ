"""/server-monitor/ws accepts only one-time stream tickets of active admins."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

import app.database as database_module
from app.auth import create_access_token
from app.database import Base
from app.models import User, UserRole
from app.routers import server_monitor
from app.services.stream_ticket import issue_stream_ticket


@pytest.fixture
def ws(monkeypatch):
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
    yield SimpleNamespace(client=TestClient(app), factory=factory)
    engine.dispose()


def _ticket(ws, username: str, stream: str = "server_monitor") -> str:
    with ws.factory() as db:
        return issue_stream_ticket(db.query(User).filter(User.username == username).one(), stream)


def _assert_rejected(client: TestClient, query: str) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/server-monitor/ws?{query}") as conn:
            conn.receive_json()
    assert exc_info.value.code == 1008


def test_ws_rejects_missing_ticket(ws):
    _assert_rejected(ws.client, "iface=eth0")


def test_ws_rejects_access_token_in_query(ws):
    token = create_access_token({"sub": "admin"})
    _assert_rejected(ws.client, f"token={token}")
    _assert_rejected(ws.client, f"ticket={token}")


def test_ws_rejects_non_admin_ticket(ws):
    _assert_rejected(ws.client, f"ticket={_ticket(ws, 'alice')}")


def test_ws_rejects_inactive_admin_ticket(ws):
    _assert_rejected(ws.client, f"ticket={_ticket(ws, 'retired')}")


def test_ws_rejects_ticket_for_another_stream(ws):
    _assert_rejected(ws.client, f"ticket={_ticket(ws, 'admin', 'monitoring')}")


def test_ws_streams_metrics_once_per_ticket(ws):
    ticket = _ticket(ws, "admin")
    with ws.client.websocket_connect(f"/server-monitor/ws?ticket={ticket}") as conn:
        assert conn.receive_json()["cpu_percent"] == 1.0

    _assert_rejected(ws.client, f"ticket={ticket}")
