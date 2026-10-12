"""Choosing the node that carries Telegram traffic."""

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


@pytest.mark.parametrize("node_id", [2, 3])
def test_unencrypted_or_local_node_is_refused(client, factory, node_id):
    response = client.put("/api/settings/telegram/relay", json={"node_id": node_id})
    assert response.status_code == 400
    with factory() as db:
        assert _get_setting(db, "telegram_relay_node_id") == ""


def test_failed_check_rolls_back_choice(client, factory, monkeypatch):
    monkeypatch.setattr(settings_telegram, "delete_webhook_sync", lambda _token: (False, "Узел «nl-mtls»: таймаут"))

    response = client.put("/api/settings/telegram/relay", json={"node_id": 1})

    assert response.status_code == 502
    assert "nl-mtls" in response.json()["detail"]
    with factory() as db:
        assert _get_setting(db, "telegram_relay_node_id") == ""


def test_successful_choice_is_saved_and_listed(client, factory, monkeypatch):
    monkeypatch.setattr(settings_telegram, "delete_webhook_sync", lambda _token: (True, ""))
    monkeypatch.setattr(settings_telegram, "_configure_bot_menu", lambda _token: None)

    response = client.put("/api/settings/telegram/relay", json={"node_id": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["relay_node_id"] == 1
    assert body["relay_nodes"] == [{"id": 1, "name": "nl-mtls"}]
    with factory() as db:
        assert _get_setting(db, "telegram_mini_app_url").endswith("/api/tg-mini")
