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


def test_relay_node_downgraded_to_plain_http_is_not_used(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import database
    from app.models import Node
    from app.services import node_manager
    from app.services.app_setting_store import _set_setting

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(Node(id=1, name="nl-1", host="203.0.113.1", mtls_enabled=False, transport="http"))
        _set_setting(db, telegram_transport.RELAY_NODE_SETTING, "1")
        db.commit()
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(node_manager, "get_adapter_for_node", lambda _node: pytest.fail("token sent over plain HTTP"))

    with pytest.raises(telegram_transport.TelegramRelayError, match="не шифруется"):
        telegram_transport.bot_api_post_sync(TOKEN, "getMe")
    engine.dispose()


def test_old_agent_without_relay_gives_update_hint(monkeypatch):
    def relay(*_args):
        raise HTTPException(status_code=404, detail="Not Found")

    monkeypatch.setattr(
        telegram_transport, "_relay_adapter", lambda: SimpleNamespace(telegram_bot_api=relay, node_name="nl-1", close=lambda: None)
    )

    with pytest.raises(telegram_transport.TelegramRelayError, match="1.13.0"):
        telegram_transport.bot_api_post_sync(TOKEN, "getMe")


def test_oidc_token_exchange_goes_through_relay_node(monkeypatch):
    seen = {}

    def relay(body, authorization):
        seen.update(body=body, authorization=authorization)
        return {"status": 200, "body": {"id_token": "idt"}}

    monkeypatch.setattr(
        telegram_transport,
        "_relay_adapter",
        lambda: SimpleNamespace(telegram_oidc_token=relay, node_name="nl-1", close=lambda: None),
    )
    monkeypatch.setattr(httpx, "post", lambda *_a, **_k: pytest.fail("OIDC went direct"))

    status, body = telegram_transport.oidc_token_exchange_sync({"code": "c1"}, client_id="bot", client_secret="secret")

    assert (status, body) == (200, {"id_token": "idt"})
    assert seen["body"] == b"code=c1"
    assert seen["authorization"] == "Basic Ym90OnNlY3JldA=="
