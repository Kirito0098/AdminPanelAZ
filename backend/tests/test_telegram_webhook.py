"""Telegram webhook: secret header + cheap mini_app_url (no full settings DTO)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.routers import telegram_webhook as tw
from app.services.telegram_webhook_security import (
    TELEGRAM_SECRET_TOKEN_HEADER,
    secrets_match,
)


def test_secrets_match_accepts_equal_and_rejects_mismatch():
    assert secrets_match("abc", "abc") is True
    assert secrets_match("abc", "abd") is False
    assert secrets_match("", "abc") is False
    assert secrets_match(None, "abc") is False
    assert secrets_match("abc", None) is False


def test_mini_app_url_uses_request_root(monkeypatch):
    monkeypatch.setattr(tw, "get_settings", lambda: SimpleNamespace(behind_nginx=False))
    monkeypatch.setattr(
        tw,
        "resolve_request_url_root",
        lambda request, behind_nginx: "https://panel.example",
    )
    request = MagicMock()
    assert tw._mini_app_url(request) == "https://panel.example/api/tg-mini"


def test_webhook_allows_missing_secret_header_legacy(monkeypatch):
    monkeypatch.setattr(tw, "_ensure_telegram_module", lambda: None)
    secret = "secret-value-32chars___________"
    monkeypatch.setattr(
        tw,
        "_get_setting",
        lambda db, key, default="": {
            "telegram_bot_interactive_enabled": "true",
            "telegram_webhook_secret": secret,
        }.get(key, default),
    )
    monkeypatch.setattr(tw, "get_telegram_webhook_client_ip", lambda _r: "149.154.160.1")
    monkeypatch.setattr(tw, "is_telegram_ip", lambda _ip: True)
    monkeypatch.setattr(tw, "consume_webhook_rate_limit", lambda _ip: None)
    monkeypatch.setattr(tw, "get_settings", lambda: SimpleNamespace(behind_nginx=True))
    monkeypatch.setattr(
        tw,
        "resolve_request_url_root",
        lambda request, behind_nginx: "https://panel.example",
    )

    handle = AsyncMock()
    monkeypatch.setattr(tw.telegram_bot_service, "handle_update", handle)

    request = MagicMock()
    request.headers.get = MagicMock(return_value=None)
    request.json = AsyncMock(return_value={"update_id": 1})
    db = MagicMock()

    result = asyncio.run(tw.telegram_webhook(secret, request, db))

    assert result == {"ok": True}
    handle.assert_awaited_once()


def test_webhook_rejects_wrong_secret_header(monkeypatch):
    monkeypatch.setattr(tw, "_ensure_telegram_module", lambda: None)
    secret = "secret-value-32chars___________"
    monkeypatch.setattr(
        tw,
        "_get_setting",
        lambda db, key, default="": {
            "telegram_bot_interactive_enabled": "true",
            "telegram_webhook_secret": secret,
        }.get(key, default),
    )
    request = MagicMock()
    request.headers.get = MagicMock(
        side_effect=lambda name, default=None: (
            "wrong-header-secret-32chars_______"
            if name == TELEGRAM_SECRET_TOKEN_HEADER
            else default
        )
    )
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(tw.telegram_webhook(secret, request, db))
    assert exc.value.status_code == 403


def test_webhook_happy_path_skips_full_settings_dto(monkeypatch):
    monkeypatch.setattr(tw, "_ensure_telegram_module", lambda: None)
    secret = "secret-value-32chars___________"
    monkeypatch.setattr(
        tw,
        "_get_setting",
        lambda db, key, default="": {
            "telegram_bot_interactive_enabled": "true",
            "telegram_webhook_secret": secret,
        }.get(key, default),
    )
    monkeypatch.setattr(tw, "get_telegram_webhook_client_ip", lambda _r: "149.154.160.1")
    monkeypatch.setattr(tw, "is_telegram_ip", lambda _ip: True)
    monkeypatch.setattr(tw, "consume_webhook_rate_limit", lambda _ip: None)
    monkeypatch.setattr(tw, "get_settings", lambda: SimpleNamespace(behind_nginx=True))
    monkeypatch.setattr(
        tw,
        "resolve_request_url_root",
        lambda request, behind_nginx: "https://panel.example",
    )

    handle = AsyncMock()
    monkeypatch.setattr(tw.telegram_bot_service, "handle_update", handle)

    request = MagicMock()
    request.headers.get = MagicMock(
        side_effect=lambda name, default=None: (
            secret if name == TELEGRAM_SECRET_TOKEN_HEADER else default
        )
    )
    request.json = AsyncMock(return_value={"update_id": 1})
    db = MagicMock()

    result = asyncio.run(tw.telegram_webhook(secret, request, db))

    assert result == {"ok": True}
    handle.assert_awaited_once()
    kwargs = handle.await_args.kwargs
    assert kwargs["mini_app_url"] == "https://panel.example/api/tg-mini"


def test_webhook_rejects_bad_url_secret_even_with_header(monkeypatch):
    monkeypatch.setattr(tw, "_ensure_telegram_module", lambda: None)
    secret = "secret-value-32chars___________"
    monkeypatch.setattr(
        tw,
        "_get_setting",
        lambda db, key, default="": {
            "telegram_bot_interactive_enabled": "true",
            "telegram_webhook_secret": secret,
        }.get(key, default),
    )
    request = MagicMock()
    request.headers.get = MagicMock(return_value=secret)
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(tw.telegram_webhook("wrong-secret-value-32chars_______", request, db))
    assert exc.value.status_code == 403
