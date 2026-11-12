"""Mini App public config + the admin surface that was removed.

``GET /tg-mini/config`` is the only unauthenticated Mini App endpoint: it feeds
the bot link on the login/error screen, so it must never carry the bot token.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.routers import tg_mini
from app.services.app_setting_store import _set_setting


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
    app = FastAPI()
    app.include_router(tg_mini.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_public_config_needs_no_token_and_hides_the_bot_token(client, db):
    _set_setting(db, "telegram_bot_token", "123456:very-secret-token")
    _set_setting(db, "telegram_bot_username", "@az_bot")
    db.commit()

    response = client.get("/api/tg-mini/config")

    assert response.status_code == 200, response.text
    assert response.json() == {"bot_username": "az_bot", "bot_configured": True}
    assert "very-secret-token" not in response.text


def test_public_config_without_settings(client):
    response = client.get("/api/tg-mini/config")

    assert response.status_code == 200, response.text
    assert response.json() == {"bot_username": None, "bot_configured": False}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/tg-mini/dashboard"),
        ("GET", "/api/tg-mini/visible-vpn-profiles"),
        ("GET", "/api/tg-mini/nodes/1"),
        ("POST", "/api/tg-mini/nodes/1/health"),
    ],
)
def test_removed_admin_routes_are_gone(client, method, path):
    response = client.request(method, path)

    assert response.status_code == 404, response.text
