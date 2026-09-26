"""OpenVPN management ``kill``: the client name must stay a single command argument."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from app.services.openvpn_management import OpenVpnManagementService

INJECTIONS = [
    "bob\nsignal SIGTERM",
    "bob\r\nexit",
    "bob signal",
    "bob\tsignal",
    "bob\x00",
    "bob\x7f",
]


@pytest.fixture
def service(tmp_path, monkeypatch):
    socket_path = tmp_path / "antizapret-udp.sock"
    socket_path.touch()
    svc = OpenVpnManagementService()
    sent: list[str] = []

    def fake_query(_path, command, *args, **kwargs):
        sent.append(command)
        return "SUCCESS: common name 'bob' found, 1 client(s) killed"

    monkeypatch.setattr(svc, "openvpn_socket_path", lambda _profile: socket_path)
    monkeypatch.setattr(svc, "query_openvpn_management_socket", fake_query)
    return svc, sent


@pytest.mark.parametrize("client_name", INJECTIONS + [""])
def test_kill_rejects_names_that_break_the_command_line(service, client_name):
    svc, sent = service

    result = svc.kill_client("antizapret-udp", client_name)

    assert result["success"] is False
    assert sent == []


@pytest.mark.parametrize("client_name", ["bob", "user_1-a", "cn.with.dots@example"])
def test_kill_sends_valid_names(service, client_name):
    svc, sent = service

    result = svc.kill_client("antizapret-udp", client_name)

    assert result["success"] is True
    assert sent == [f"kill {client_name}"]


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "n" * 32)
    os.environ.pop("NODE_AGENT_ALLOWED_IPS", None)
    from fastapi.testclient import TestClient

    import node_agent.main as agent_main

    kill = MagicMock(return_value={"success": True})
    monkeypatch.setattr(agent_main.openvpn_management_service, "kill_client", kill)
    return TestClient(agent_main.app), {"X-Node-Key": agent_main.NODE_AGENT_API_KEY}, kill


@pytest.mark.parametrize("client_name", INJECTIONS)
def test_agent_kill_endpoint_rejects_injected_names(agent, client_name):
    client, headers, kill = agent

    response = client.post(
        "/openvpn/management/kill",
        json={"unit": "antizapret-udp", "client_name": client_name},
        headers=headers,
    )

    assert response.status_code == 422
    kill.assert_not_called()


def test_agent_kill_endpoint_passes_valid_names(agent):
    client, headers, kill = agent

    response = client.post(
        "/openvpn/management/kill",
        json={"unit": "antizapret-udp", "client_name": "bob"},
        headers=headers,
    )

    assert response.status_code == 200
    kill.assert_called_once_with("antizapret-udp", "bob")
