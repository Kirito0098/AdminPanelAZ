"""Telegram OIDC callback accepts only the state issued to the same browser."""

from __future__ import annotations

from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from starlette.requests import Request

from app.models import User, UserRole
from app.routers import auth as auth_router


class _Features:
    def is_enabled(self, _name):
        return True


@pytest.fixture(autouse=True)
def _oidc(monkeypatch):
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", lambda: _Features())
    monkeypatch.setattr(auth_router, "_get_telegram_oidc_settings", lambda _db: (True, "cid", "secret"))
    monkeypatch.setattr(auth_router, "_telegram_oidc_callback_url", lambda _request: "https://panel.example/cb")


def _request(query: bytes = b"", cookie: str | None = None) -> Request:
    headers = [(b"user-agent", b"pytest")]
    if cookie is not None:
        headers.append((b"cookie", cookie.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/telegram/oidc/callback",
            "headers": headers,
            "client": ("10.0.0.7", 50000),
            "query_string": query,
        }
    )


def _set_cookies(response) -> list[str]:
    return response.headers.getlist("set-cookie")


def test_start_sets_state_cookie(monkeypatch):
    seen: dict = {}

    def _build(**kwargs):
        seen.update(kwargs)
        return "https://oauth.telegram.org/auth?x=1"

    monkeypatch.setattr(auth_router, "build_authorization_url", _build)

    response = auth_router.telegram_oidc_start(_request(), MagicMock())

    cookie = next(c for c in _set_cookies(response) if c.startswith("tg_oidc_state="))
    assert cookie.startswith(f"tg_oidc_state={seen['state']};")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=600" in cookie


@pytest.mark.parametrize("cookie", [None, "tg_oidc_state=other"])
def test_callback_rejects_state_from_another_browser(monkeypatch, cookie):
    pop = MagicMock(return_value={"redirect_uri": "x", "code_verifier": "v"})
    monkeypatch.setattr(auth_router, "pop_oidc_state", pop)

    response = auth_router.telegram_oidc_callback(_request(b"code=c&state=s", cookie), MagicMock())

    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert "tg_error" in query
    pop.assert_not_called()
    assert any(c.startswith('tg_oidc_state=""') for c in _set_cookies(response))


def test_callback_with_matching_cookie_logs_in_and_clears_it(monkeypatch):
    user = User(id=1, username="tg-alice", password_hash="x", role=UserRole.admin, is_active=True)
    monkeypatch.setattr(auth_router, "pop_oidc_state", lambda _s: {"redirect_uri": "x", "code_verifier": "v"})
    monkeypatch.setattr(auth_router, "exchange_authorization_code", lambda **_k: {"id_token": "idt"})
    monkeypatch.setattr(auth_router, "verify_id_token", lambda *_a, **_k: {"sub": "777"})
    monkeypatch.setattr(auth_router, "telegram_id_from_claims", lambda _c: "777")
    monkeypatch.setattr(auth_router, "_complete_telegram_login", lambda _db, _req, _tg, mini=False: user)
    monkeypatch.setattr(
        auth_router,
        "_telegram_login_redirect",
        lambda _u, _db, _req: RedirectResponse(url="/login#token=t", status_code=302),
    )

    response = auth_router.telegram_oidc_callback(
        _request(b"code=c&state=s", "tg_oidc_state=s"), MagicMock()
    )

    assert response.headers["location"] == "/login#token=t"
    assert any(c.startswith('tg_oidc_state=""') for c in _set_cookies(response))


def test_callback_clears_cookie_when_token_exchange_raises_http_exception(monkeypatch):
    def _exchange(**_k):
        raise HTTPException(status_code=502, detail="Telegram недоступен")

    monkeypatch.setattr(auth_router, "pop_oidc_state", lambda _s: {"redirect_uri": "x", "code_verifier": "v"})
    monkeypatch.setattr(auth_router, "exchange_authorization_code", _exchange)

    response = auth_router.telegram_oidc_callback(
        _request(b"code=c&state=s", "tg_oidc_state=s"), MagicMock()
    )

    assert response.status_code == 502
    assert response.body == '{"detail":"Telegram недоступен"}'.encode()
    assert any(c.startswith('tg_oidc_state=""') for c in _set_cookies(response))


def test_callback_clears_cookie_when_token_exchange_fails_on_network(monkeypatch):
    def _exchange(**_k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(auth_router, "pop_oidc_state", lambda _s: {"redirect_uri": "x", "code_verifier": "v"})
    monkeypatch.setattr(auth_router, "exchange_authorization_code", _exchange)

    response = auth_router.telegram_oidc_callback(
        _request(b"code=c&state=s", "tg_oidc_state=s"), MagicMock()
    )

    assert "tg_error" in parse_qs(urlsplit(response.headers["location"]).query)
    assert any(c.startswith('tg_oidc_state=""') for c in _set_cookies(response))
