"""Mini App static assets: the entry bundle is public, lazy chunks need a signed marker.

The Mini App renders before it signs in, so index.html, its entry chunk and CSS must stay
public. Admin screens ship as lazy chunks and are served only with the marker cookie that
``POST /auth`` sets — an anonymous visitor must get 404, not the admin screen source.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import get_settings
from app.database import get_db
from app.routers import tg_mini as root
from app.routers.tg_mini.static import mini_app_asset
from app.services.tg_mini_asset_marker import (
    TG_MINI_ASSET_COOKIE,
    TG_MINI_ASSET_MAX_AGE,
    issue_tg_mini_asset_marker,
    tg_mini_asset_marker_valid,
)

ENTRY = "tg-mini-entry.js"
SHARED = "tg-mini-shared.js"
LAZY = "tg-mini-clients.js"


@pytest.fixture()
def static_dir(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "index.html").write_text(
        f'<script type="module" src="./assets/{ENTRY}" nonce="%CSP_NONCE%"></script>', encoding="utf-8"
    )
    (assets / ENTRY).write_text(f'import"./{SHARED}";', encoding="utf-8")
    (assets / SHARED).write_text("shared", encoding="utf-8")
    (assets / LAZY).write_text("admin screen source", encoding="utf-8")
    (assets / "tg-mini.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "assets.bak").mkdir()
    (tmp_path / "assets.bak" / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(root, "_STATIC_DIR", tmp_path)
    return tmp_path


@pytest.fixture()
def client(static_dir):
    app = FastAPI()
    app.include_router(root.router, prefix="/api")
    return TestClient(app)


def _request(cookies: dict[str, str] | None = None) -> Request:
    headers = []
    if cookies:
        headers.append((b"cookie", "; ".join(f"{key}={value}" for key, value in cookies.items()).encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def _marker(telegram_id: str = "12345", *, max_age: int = 3600, now: float | None = None) -> str:
    return issue_tg_mini_asset_marker(
        get_settings().secret_key,
        telegram_id,
        max_age=max_age,
        now=now,
    )


def test_entry_chunk_is_public(client):
    response = client.get(f"/api/tg-mini/assets/{ENTRY}")

    assert response.status_code == 200
    assert "import" in response.text


def test_static_import_of_entry_chunk_is_public(client):
    response = client.get(f"/api/tg-mini/assets/{SHARED}")

    assert response.status_code == 200


def test_css_is_public(client):
    response = client.get("/api/tg-mini/assets/tg-mini.css")

    assert response.status_code == 200


def test_lazy_chunk_is_hidden_from_anonymous_visitor(client):
    response = client.get(f"/api/tg-mini/assets/{LAZY}")

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert "admin screen source" not in response.text


def test_lazy_chunk_is_served_with_valid_marker(client):
    client.cookies.set(TG_MINI_ASSET_COOKIE, _marker())

    response = client.get(f"/api/tg-mini/assets/{LAZY}")

    assert response.status_code == 200
    assert response.text == "admin screen source"
    assert response.headers["cache-control"] == "private, no-cache"
    assert response.headers["vary"] == "Cookie"


@pytest.mark.parametrize(
    "cookie",
    [
        # expired: issued 13 hours ago with the 12 hour TTL
        issue_tg_mini_asset_marker(
            get_settings().secret_key,
            "12345",
            now=time.time() - (TG_MINI_ASSET_MAX_AGE + 3600),
        ),
        # forged: valid shape, signature of another id
        f"99999.{int(time.time()) + 3600}.{_marker('12345').rsplit('.', 1)[1]}",
        "not-a-marker",
        "",
    ],
)
def test_lazy_chunk_is_hidden_with_expired_or_forged_marker(client, cookie):
    client.cookies.set(TG_MINI_ASSET_COOKIE, cookie)

    response = client.get(f"/api/tg-mini/assets/{LAZY}")

    assert response.status_code == 404


def test_lazy_chunk_is_hidden_for_marker_of_another_secret(client):
    foreign = issue_tg_mini_asset_marker("another-secret-key", "12345")
    client.cookies.set(TG_MINI_ASSET_COOKIE, foreign)

    assert client.get(f"/api/tg-mini/assets/{LAZY}").status_code == 404


def test_marker_ttl_is_twelve_hours():
    assert TG_MINI_ASSET_MAX_AGE == 12 * 3600


def test_without_index_html_every_chunk_is_hidden(static_dir, monkeypatch):
    (static_dir / "index.html").unlink()

    with pytest.raises(HTTPException) as exc:
        mini_app_asset(ENTRY, _request())

    assert exc.value.status_code == 404
    assert exc.value.headers == {"Cache-Control": "no-store"}


def test_sibling_directory_assets_bak_is_not_served(static_dir):
    with pytest.raises(HTTPException) as exc:
        mini_app_asset("../assets.bak/secret.txt", _request())

    assert exc.value.status_code == 404


def test_marker_validation_helper():
    secret = get_settings().secret_key
    marker = issue_tg_mini_asset_marker(secret, "12345")

    assert tg_mini_asset_marker_valid(secret, marker)
    assert not tg_mini_asset_marker_valid(secret, marker, now=time.time() + TG_MINI_ASSET_MAX_AGE + 1)
    assert not tg_mini_asset_marker_valid("another-secret-key", marker)
    assert not tg_mini_asset_marker_valid(secret, marker[:-2] + "AA")
    assert not tg_mini_asset_marker_valid(secret, None)


@pytest.fixture()
def auth_client(monkeypatch):
    app = FastAPI()
    app.include_router(root.router, prefix="/api")
    user = SimpleNamespace(username="alice", is_active=True, token_version=0, telegram_id="12345")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(root, "_get_bot_token", lambda _db: "123:token")
    monkeypatch.setattr(root, "_get_setting", lambda _db, _key: "")
    return TestClient(app)


def test_successful_auth_sets_asset_marker_cookie(auth_client, monkeypatch):
    monkeypatch.setattr(root, "_verify_telegram_init_data", lambda *a, **k: {"id": "12345"})

    response = auth_client.post("/api/tg-mini/auth", json={"init_data": "signed"})

    assert response.status_code == 200, response.text
    marker_cookie = next(
        header for header in response.headers.get_list("set-cookie") if header.startswith(f"{TG_MINI_ASSET_COOKIE}=")
    )
    assert f"Max-Age={TG_MINI_ASSET_MAX_AGE}" in marker_cookie
    assert "Path=/" in marker_cookie
    assert "HttpOnly" in marker_cookie
    assert "SameSite=lax" in marker_cookie
    assert tg_mini_asset_marker_valid(get_settings().secret_key, auth_client.cookies.get(TG_MINI_ASSET_COOKIE))


def test_failed_auth_does_not_set_asset_marker_cookie(auth_client, monkeypatch):
    def _reject(*_args, **_kwargs):
        raise ValueError("Неверная подпись init_data")

    monkeypatch.setattr(root, "_verify_telegram_init_data", _reject)

    response = auth_client.post("/api/tg-mini/auth", json={"init_data": "bad"})

    assert response.status_code == 401
    assert not any(
        header.startswith(f"{TG_MINI_ASSET_COOKIE}=") for header in response.headers.get_list("set-cookie")
    )
    assert auth_client.cookies.get(TG_MINI_ASSET_COOKIE) is None


def test_unlinked_account_does_not_set_asset_marker_cookie(auth_client, monkeypatch):
    monkeypatch.setattr(root, "_verify_telegram_init_data", lambda *a, **k: {"id": "777"})
    monkeypatch.setattr(root.admin_notify_service, "send_tg_login_unlinked", lambda *_a, **_k: None)
    empty_db = MagicMock()
    empty_db.query.return_value.filter.return_value.first.return_value = None
    auth_client.app.dependency_overrides[get_db] = lambda: empty_db

    response = auth_client.post("/api/tg-mini/auth", json={"init_data": "signed"})

    assert response.status_code == 401
    assert not any(
        header.startswith(f"{TG_MINI_ASSET_COOKIE}=") for header in response.headers.get_list("set-cookie")
    )
