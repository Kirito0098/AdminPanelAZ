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


def _use_nodes(monkeypatch, adapters: dict[int, object]) -> None:
    monkeypatch.setattr(telegram_transport, "relay_node_ids", lambda: list(adapters))
    monkeypatch.setattr(telegram_transport, "_relay_adapter_for", lambda node_id: adapters[node_id])
    monkeypatch.setattr(telegram_transport, "_failed_until", {})


def _bot_adapter(name: str, reply, calls: list[str] | None = None):
    def telegram_bot_api(*_args, **_kwargs):
        if calls is not None:
            calls.append(name)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return SimpleNamespace(telegram_bot_api=telegram_bot_api, node_name=name, close=lambda: None)


def test_without_relay_node_calls_telegram_directly(monkeypatch, direct):
    monkeypatch.setattr(telegram_transport, "relay_node_ids", lambda: [])

    body = telegram_transport.bot_api_post_sync(TOKEN, "getMe")

    assert body == {"ok": True, "result": {"id": 1}}
    assert str(direct[0].url) == f"https://api.telegram.org/bot{TOKEN}/getMe"


def test_with_relay_node_sends_multipart_through_agent(monkeypatch, direct):
    seen = {}

    def relay(token, method, body, content_type, *, timeout):
        seen.update(token=token, method=method, body=body, content_type=content_type)
        return {"status": 200, "body": {"ok": True, "result": True}}

    adapter = SimpleNamespace(telegram_bot_api=relay, node_name="nl-1", close=lambda: None)
    _use_nodes(monkeypatch, {1: adapter})

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
        _set_setting(db, telegram_transport.RELAY_NODES_SETTING, "1")
        db.commit()
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(node_manager, "get_adapter_for_node", lambda _node: pytest.fail("token sent over plain HTTP"))

    with pytest.raises(telegram_transport.TelegramRelayError, match="не шифруется"):
        telegram_transport.bot_api_post_sync(TOKEN, "getMe")
    engine.dispose()


def test_relay_call_fails_fast_on_dead_node_and_keeps_caller_read_timeout(monkeypatch):
    seen = {}

    def relay(*_args, timeout):
        seen["timeout"] = timeout
        return OK

    _use_nodes(monkeypatch, {1: SimpleNamespace(telegram_bot_api=relay, node_name="nl-1", close=lambda: None)})

    telegram_transport.bot_api_post_sync(TOKEN, "getUpdates", timeout=40)

    assert seen["timeout"].connect == telegram_transport.RELAY_CONNECT_TIMEOUT
    assert seen["timeout"].read == 40 + telegram_transport.RELAY_OVERHEAD_SECONDS


def test_ssh_tunnel_failure_hands_request_to_next_node(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import database
    from app.models import Node
    from app.services import node_manager
    from app.services.app_setting_store import _set_setting
    from app.services.ssh_tunnel_pool import SshTunnelError

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(Node(id=1, name="nl-1", host="203.0.113.1", mtls_enabled=True))
        db.add(Node(id=2, name="de-2", host="203.0.113.2", mtls_enabled=True))
        _set_setting(db, telegram_transport.RELAY_NODES_SETTING, "1,2")
        db.commit()
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(telegram_transport, "_failed_until", {})

    def adapter_for(node):
        if node.id == 1:
            raise SshTunnelError("ssh_unreachable", "SSH host is unreachable")
        return _bot_adapter("de-2", OK)

    monkeypatch.setattr(node_manager, "get_adapter_for_node", adapter_for)

    assert telegram_transport.bot_api_post_sync(TOKEN, "getMe") == {"ok": True, "result": True}
    assert telegram_transport.last_relay_node_name() == "de-2"
    engine.dispose()


def test_old_agent_without_relay_gives_update_hint(monkeypatch):
    def relay(*_args, **_kwargs):
        raise HTTPException(status_code=404, detail="Not Found")

    _use_nodes(monkeypatch, {1: SimpleNamespace(telegram_bot_api=relay, node_name="nl-1", close=lambda: None)})

    with pytest.raises(telegram_transport.TelegramRelayError, match="1.13.0"):
        telegram_transport.bot_api_post_sync(TOKEN, "getMe")


def test_oidc_token_exchange_goes_through_relay_node(monkeypatch):
    seen = {}

    def relay(body, authorization):
        seen.update(body=body, authorization=authorization)
        return {"status": 200, "body": {"id_token": "idt"}}

    _use_nodes(monkeypatch, {1: SimpleNamespace(telegram_oidc_token=relay, node_name="nl-1", close=lambda: None)})
    monkeypatch.setattr(httpx, "post", lambda *_a, **_k: pytest.fail("OIDC went direct"))

    status, body = telegram_transport.oidc_token_exchange_sync({"code": "c1"}, client_id="bot", client_secret="secret")

    assert (status, body) == (200, {"id_token": "idt"})
    assert seen["body"] == b"code=c1"
    assert seen["authorization"] == "Basic Ym90OnNlY3JldA=="


OK = {"status": 200, "body": {"ok": True, "result": True}}


def test_failed_node_hands_request_to_next(monkeypatch):
    _use_nodes(
        monkeypatch,
        {1: _bot_adapter("nl-1", HTTPException(status_code=502, detail="таймаут")), 2: _bot_adapter("de-2", OK)},
    )

    assert telegram_transport.bot_api_post_sync(TOKEN, "getMe") == {"ok": True, "result": True}
    assert telegram_transport.last_relay_node_name() == "de-2"


def test_failed_node_is_skipped_until_cooldown_ends(monkeypatch):
    calls: list[str] = []
    clock = {"now": 1000.0}
    monkeypatch.setattr(telegram_transport.time, "monotonic", lambda: clock["now"])
    _use_nodes(
        monkeypatch,
        {
            1: _bot_adapter("nl-1", HTTPException(status_code=502, detail="таймаут"), calls),
            2: _bot_adapter("de-2", OK, calls),
        },
    )

    telegram_transport.bot_api_post_sync(TOKEN, "getMe")
    telegram_transport.bot_api_post_sync(TOKEN, "getMe")
    clock["now"] += telegram_transport.FAILED_NODE_COOLDOWN_SECONDS + 1
    telegram_transport.bot_api_post_sync(TOKEN, "getMe")

    assert calls == ["nl-1", "de-2", "de-2", "nl-1", "de-2"]


def test_telegram_error_does_not_switch_node(monkeypatch):
    calls: list[str] = []
    refused = {"status": 400, "body": {"ok": False, "description": "chat not found"}}
    _use_nodes(monkeypatch, {1: _bot_adapter("nl-1", refused, calls), 2: _bot_adapter("de-2", OK, calls)})

    assert telegram_transport.bot_api_post_sync(TOKEN, "getMe") == refused["body"]
    assert calls == ["nl-1"]


def test_all_nodes_failed_reports_each(monkeypatch):
    _use_nodes(
        monkeypatch,
        {
            1: _bot_adapter("nl-1", HTTPException(status_code=502, detail="таймаут")),
            2: _bot_adapter("de-2", HTTPException(status_code=404, detail="Not Found")),
        },
    )

    with pytest.raises(telegram_transport.TelegramRelayError, match="nl-1.*таймаут.*de-2.*1.13.0"):
        telegram_transport.bot_api_post_sync(TOKEN, "getMe")
