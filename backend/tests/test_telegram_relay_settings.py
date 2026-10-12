"""Choosing the ordered list of nodes that carry Telegram traffic."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.database import Base, get_db
from app.models import Node, UserRole
from app.routers import settings_telegram
from app.services.app_setting_store import _get_setting, _set_setting
from app.services.telegram_transport import TelegramRelayError


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all(
            [
                Node(id=1, name="nl-mtls", host="203.0.113.1", mtls_enabled=True),
                Node(id=2, name="plain-http", host="203.0.113.2"),
                Node(id=3, name="local", host="127.0.0.1", is_local=True),
                Node(id=4, name="de-mtls", host="203.0.113.4", mtls_enabled=True),
            ]
        )
        _set_setting(db, "telegram_bot_token", "123456:" + "A" * 35)
        db.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def client(factory):
    app = FastAPI()
    app.include_router(settings_telegram.router, prefix="/api")

    def _db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: type(
        "U", (), {"id": 1, "username": "admin", "role": UserRole.admin}
    )()
    with patch.object(settings_telegram, "admin_notify_service"):
        yield TestClient(app)


def _nodes_answer(monkeypatch, working: set[int]) -> None:
    def call_via_node(node_id, _call):
        if node_id not in working:
            raise TelegramRelayError(f"Узел #{node_id}: таймаут")
        return {"status": 200, "body": {"ok": True, "result": {}}}, f"node-{node_id}"

    monkeypatch.setattr(settings_telegram, "call_via_node", call_via_node)
    monkeypatch.setattr(settings_telegram, "mark_relay_node_failed", lambda _node_id: None)
    monkeypatch.setattr(settings_telegram, "delete_webhook_sync", lambda _token: (True, ""))
    monkeypatch.setattr(settings_telegram, "_configure_bot_menu", lambda _token: None)


@pytest.mark.parametrize("node_ids", [[2], [1, 3]])
def test_unencrypted_or_local_node_is_refused(client, factory, node_ids):
    response = client.put("/api/settings/telegram/relay", json={"node_ids": node_ids})
    assert response.status_code == 400
    with factory() as db:
        assert _get_setting(db, "telegram_relay_node_ids") == ""


def test_saved_in_order_when_one_node_works(client, factory, monkeypatch):
    _nodes_answer(monkeypatch, working={1})

    response = client.put("/api/settings/telegram/relay", json={"node_ids": [4, 1]})

    assert response.status_code == 200
    body = response.json()
    assert body["relay_node_ids"] == [4, 1]
    assert [(c["id"], c["ok"]) for c in body["relay_check"]] == [(4, False), (1, True)]
    assert "таймаут" in body["relay_check"][0]["error"]
    assert [(n["name"], n["unavailable_reason"] is None) for n in body["relay_nodes"]] == [
        ("de-mtls", True),
        ("nl-mtls", True),
        ("plain-http", False),
    ]
    with factory() as db:
        assert _get_setting(db, "telegram_relay_node_ids") == "4,1"
        assert _get_setting(db, "telegram_mini_app_url").endswith("/api/tg-mini")


def test_refused_when_no_node_works(client, factory, monkeypatch):
    _nodes_answer(monkeypatch, working=set())

    response = client.put("/api/settings/telegram/relay", json={"node_ids": [1, 4]})

    assert response.status_code == 502
    assert "#1" in response.json()["detail"] and "#4" in response.json()["detail"]
    with factory() as db:
        assert _get_setting(db, "telegram_relay_node_ids") == ""


def test_failed_webhook_removal_rolls_back(client, factory, monkeypatch):
    _nodes_answer(monkeypatch, working={1})
    monkeypatch.setattr(settings_telegram, "delete_webhook_sync", lambda _token: (False, "Узел «nl-mtls»: таймаут"))

    response = client.put("/api/settings/telegram/relay", json={"node_ids": [1]})

    assert response.status_code == 502
    with factory() as db:
        assert _get_setting(db, "telegram_relay_node_ids") == ""
