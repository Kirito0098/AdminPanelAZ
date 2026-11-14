"""Mini App sign-in guardrails: per-IP rate limit and initData size bound."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.routers.tg_mini import auth as auth_module
from app.services.tg_mini_auth_rate_limit import TgMiniAuthRateLimitService

AUTH_PATH = "/api/tg-mini/auth"
CLIENT_IP = "203.0.113.7"
RATE_LIMIT_DETAIL = "Слишком много попыток входа. Повторите позже."


@pytest.fixture()
def client(monkeypatch):
    # Fresh in-memory limiter per test: the module-level one keeps its window.
    monkeypatch.setattr(auth_module, "tg_mini_auth_rate_limit_service", TgMiniAuthRateLimitService())
    monkeypatch.setattr(
        "app.routers.tg_mini.ip_restriction_service",
        SimpleNamespace(get_client_ip=lambda _request: CLIENT_IP),
    )
    # Past the limiter the handler stops here: no HMAC, no DB query, no admin notify.
    monkeypatch.setattr("app.routers.tg_mini._get_bot_token", lambda _db: "")
    app = FastAPI()
    app.include_router(auth_module.router, prefix="/api/tg-mini")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


def test_first_attempt_is_not_rate_limited(client):
    response = client.post(AUTH_PATH, json={"init_data": "x"})

    assert response.status_code == 503
    assert "Retry-After" not in response.headers


def test_21st_attempt_within_minute_returns_429_with_retry_after(client):
    for _ in range(20):
        assert client.post(AUTH_PATH, json={"init_data": "x"}).status_code == 503

    response = client.post(AUTH_PATH, json={"init_data": "x"})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {"detail": RATE_LIMIT_DETAIL}


def test_empty_init_data_is_rejected_with_422(client):
    response = client.post(AUTH_PATH, json={"init_data": ""})

    assert response.status_code == 422
    assert "Retry-After" not in response.headers


def test_oversized_init_data_is_rejected_with_422(client):
    response = client.post(AUTH_PATH, json={"init_data": "x" * 8193})

    assert response.status_code == 422
    # Boundary validation only: no traceback or server internals in the answer.
    assert "Traceback" not in response.text
