"""Node agent IP allowlist: refused clients get 403, not an internal error."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def agent_main(monkeypatch):
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "n" * 32)
    os.environ.pop("NODE_AGENT_ALLOWED_IPS", None)
    import node_agent.main as agent_main

    monkeypatch.setattr(agent_main, "NODE_AGENT_ALLOWED_IPS", ["10.0.0.0/8", "192.0.2.10"])
    return agent_main


def _client(agent_main, ip: str) -> TestClient:
    return TestClient(agent_main.app, client=(ip, 50000), raise_server_exceptions=False)


def test_ip_outside_allowlist_gets_403(agent_main):
    response = _client(agent_main, "192.0.2.5").get("/health")

    assert response.status_code == 403
    assert response.json() == {"detail": "Доступ запрещён с вашего IP"}


def test_unparseable_client_address_gets_403(agent_main):
    response = _client(agent_main, "not-an-ip").get("/health")

    assert response.status_code == 403
    assert response.json() == {"detail": "Доступ запрещён"}


@pytest.mark.parametrize("ip", ["10.1.2.3", "192.0.2.10", "::ffff:10.1.2.3"])
def test_allowlisted_ip_reaches_the_app(agent_main, ip):
    response = _client(agent_main, ip).get("/no-such-endpoint")

    assert response.status_code == 404
