"""Node agent relays Bot API calls to api.telegram.org only."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

KEY = "n" * 32
TOKEN = "123456:" + "A" * 35


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", KEY)
    import node_agent.main as agent_main

    monkeypatch.setattr(agent_main, "NODE_AGENT_API_KEY", KEY)
    monkeypatch.setattr(agent_main, "NODE_AGENT_ALLOWED_IPS", [])
    return agent_main


@pytest.fixture
def telegram(monkeypatch):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, json={"ok": False, "description": "chat not found"})

    from app.services import telegram_relay

    monkeypatch.setattr(telegram_relay, "_transport", httpx.MockTransport(handler))
    return calls


def _post(agent, method="sendMessage", token=TOKEN, key=KEY, body=b'{"chat_id":1}'):
    client = TestClient(agent.app, raise_server_exceptions=False)
    return client.post(
        f"/telegram/bot-api/{method}",
        content=body,
        headers={"X-Node-Key": key, "X-Telegram-Bot-Token": token, "Content-Type": "application/json"},
    )


def test_relay_requires_node_key(agent, telegram):
    assert _post(agent, key="x" * 32).status_code == 401
    assert telegram == []


@pytest.mark.parametrize(("method", "token"), [("send%2F..%2Fx", TOKEN), ("get.Me", TOKEN), ("sendMessage", "bad/token"), ("", TOKEN)])
def test_relay_rejects_bad_method_or_token(agent, telegram, method, token):
    assert _post(agent, method=method, token=token).status_code in (400, 404, 405)
    assert telegram == []


def test_relay_forwards_to_telegram_and_wraps_answer(agent, telegram):
    response = _post(agent)

    assert response.status_code == 200
    assert response.json() == {"status": 400, "body": {"ok": False, "description": "chat not found"}}
    sent = telegram[0]
    assert str(sent.url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert sent.content == b'{"chat_id":1}'
    assert sent.headers["content-type"] == "application/json"


@pytest.fixture
def oauth(monkeypatch):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json={"keys": [{"kid": "k1"}]})
        return httpx.Response(200, json={"id_token": "idt"})

    from app.services import telegram_relay

    monkeypatch.setattr(telegram_relay, "_transport", httpx.MockTransport(handler))
    return calls


def test_oidc_relay_requires_node_key(agent, oauth):
    client = TestClient(agent.app, raise_server_exceptions=False)
    assert client.get("/telegram/oidc/jwks", headers={"X-Node-Key": "x" * 32}).status_code == 401
    assert client.post("/telegram/oidc/token", headers={"X-Node-Key": "x" * 32}).status_code == 401
    assert oauth == []


def test_oidc_token_exchange_forwarded_to_oauth_telegram(agent, oauth):
    client = TestClient(agent.app, raise_server_exceptions=False)
    response = client.post(
        "/telegram/oidc/token",
        content=b"grant_type=authorization_code&code=c1",
        headers={
            "X-Node-Key": KEY,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Telegram-Oidc-Authorization": "Basic Ym90OnNlY3JldA==",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": 200, "body": {"id_token": "idt"}}
    sent = oauth[0]
    assert str(sent.url) == "https://oauth.telegram.org/token"
    assert sent.content == b"grant_type=authorization_code&code=c1"
    assert sent.headers["authorization"] == "Basic Ym90OnNlY3JldA=="


def test_oidc_jwks_fetched_from_fixed_url(agent, oauth):
    client = TestClient(agent.app, raise_server_exceptions=False)
    response = client.get("/telegram/oidc/jwks", headers={"X-Node-Key": KEY})

    assert response.json() == {"status": 200, "body": {"keys": [{"kid": "k1"}]}}
    assert str(oauth[0].url) == "https://oauth.telegram.org/.well-known/jwks.json"
