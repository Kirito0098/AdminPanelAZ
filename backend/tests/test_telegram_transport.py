"""Bot API calls go direct or through the chosen node agent."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.services import telegram_api, telegram_transport

TOKEN = "123456:" + "A" * 35


@pytest.fixture
def direct(monkeypatch):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"id": 1}})

    monkeypatch.setattr(telegram_api, "_bot_api_sync_client", httpx.Client(transport=httpx.MockTransport(handler)))
    return calls


def test_without_relay_node_calls_telegram_directly(monkeypatch, direct):
    monkeypatch.setattr(telegram_transport, "_relay_adapter", lambda: None)

    body = telegram_transport.bot_api_post_sync(TOKEN, "getMe")

    assert body == {"ok": True, "result": {"id": 1}}
    assert str(direct[0].url) == f"https://api.telegram.org/bot{TOKEN}/getMe"


def test_with_relay_node_sends_multipart_through_agent(monkeypatch, direct):
    seen = {}

    def relay(token, method, body, content_type):
        seen.update(token=token, method=method, body=body, content_type=content_type)
        return {"status": 200, "body": {"ok": True, "result": True}}

    adapter = SimpleNamespace(telegram_bot_api=relay, node_name="nl-1", close=lambda: None)
    monkeypatch.setattr(telegram_transport, "_relay_adapter", lambda: adapter)

    body = telegram_transport.bot_api_post_sync(
        TOKEN, "sendDocument", data={"chat_id": "1"}, files={"document": ("b.tar.gz", b"xyz", "application/gzip")}
    )

    assert body == {"ok": True, "result": True}
    assert direct == []
    assert seen["method"] == "sendDocument"
    assert seen["content_type"].startswith("multipart/form-data; boundary=")
    assert b"xyz" in seen["body"]


def test_old_agent_without_relay_gives_update_hint(monkeypatch):
    def relay(*_args):
        raise HTTPException(status_code=404, detail="Not Found")

    monkeypatch.setattr(
        telegram_transport, "_relay_adapter", lambda: SimpleNamespace(telegram_bot_api=relay, node_name="nl-1", close=lambda: None)
    )

    with pytest.raises(telegram_transport.TelegramRelayError, match="1.13.0"):
        telegram_transport.bot_api_post_sync(TOKEN, "getMe")
