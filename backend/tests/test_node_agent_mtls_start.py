"""Node agent with mTLS on but certificates missing refuses to start instead of serving plain HTTP."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def agent_main(monkeypatch, tmp_path):
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "n" * 32)
    os.environ.pop("NODE_AGENT_ALLOWED_IPS", None)
    import node_agent.main as agent_main

    monkeypatch.setattr(agent_main, "NODE_AGENT_MTLS_ENABLED", True)
    monkeypatch.setattr(agent_main, "NODE_AGENT_MTLS_SERVER_CERT", str(tmp_path / "agent.crt"))
    monkeypatch.setattr(agent_main, "NODE_AGENT_MTLS_SERVER_KEY", str(tmp_path / "agent.key"))
    monkeypatch.setattr(agent_main, "NODE_AGENT_MTLS_CA_CERT", str(tmp_path / "ca.crt"))
    return agent_main


def test_mtls_without_certificates_refuses_to_start(agent_main, tmp_path):
    (tmp_path / "ca.crt").write_text("ca")

    with pytest.raises(SystemExit) as exc:
        agent_main._uvicorn_ssl_kwargs()

    message = str(exc.value)
    assert "mTLS включён" in message
    assert "сертификатов нет" in message
    assert str(tmp_path / "agent.crt") in message
    assert str(tmp_path / "ca.crt") not in message


def test_mtls_with_certificates_passes_them_to_uvicorn(agent_main, tmp_path):
    for name in ("agent.crt", "agent.key", "ca.crt"):
        (tmp_path / name).write_text(name)

    assert agent_main._uvicorn_ssl_kwargs() == {
        "ssl_certfile": str(tmp_path / "agent.crt"),
        "ssl_keyfile": str(tmp_path / "agent.key"),
        "ssl_ca_certs": str(tmp_path / "ca.crt"),
        "ssl_cert_reqs": 2,
    }


def test_mtls_off_needs_no_certificates(agent_main, monkeypatch):
    monkeypatch.setattr(agent_main, "NODE_AGENT_MTLS_ENABLED", False)

    assert agent_main._uvicorn_ssl_kwargs() == {}


def test_health_reports_tls_from_the_mtls_flag(agent_main, monkeypatch):
    captured: dict = {}

    def fake_payload(_service, *, agent_version, listen_tls):
        captured["listen_tls"] = listen_tls
        return {}

    monkeypatch.setattr(agent_main, "build_health_payload", fake_payload)

    response = TestClient(agent_main.app).get("/health", headers={"X-Node-Key": agent_main.NODE_AGENT_API_KEY})

    assert response.status_code == 200
    assert captured == {"listen_tls": True}
