from __future__ import annotations

import httpx
import pytest
from fastapi import status

from app.services import node_link_errors as link
from app.services.node_health import NODE_AGENT_VERSION, build_health_payload


class _FakeService:
    base_path = "/opt/antizapret"

    def get_service_status(self):
        return []

    def get_antizapret_version(self):
        return "test"

    def get_server_ip(self):
        return "1.2.3.4"


def test_node_agent_version_is_1_8_0():
    assert NODE_AGENT_VERSION == "1.8.0"


def test_build_health_payload_includes_uptime_and_optional_tls():
    payload = build_health_payload(_FakeService(), listen_tls=True)
    assert "started_at" in payload
    assert isinstance(payload["uptime_sec"], int)
    assert payload["uptime_sec"] >= 0
    assert payload["listen_tls"] is True
    assert payload["agent_version"] == "1.8.0"


def test_classify_401_is_node_auth():
    code, message = link.classify_http_status(401, "nope", mtls_enabled=False)
    assert code == link.CODE_AUTH
    assert "X-Node-Key" in message


def test_classify_timeout():
    code, _ = link.classify_request_error(httpx.TimeoutException("t"), mtls_enabled=False)
    assert code == link.CODE_TIMEOUT
    assert link.http_status_for_code(code) == status.HTTP_504_GATEWAY_TIMEOUT


def test_classify_wrong_version_ssl():
    exc = httpx.ConnectError("WRONG_VERSION_NUMBER")
    code, message = link.classify_request_error(exc, mtls_enabled=False)
    assert code == link.CODE_TLS_MISMATCH
    assert "WRONG_VERSION_NUMBER" in message


def test_raise_link_error_uses_502_for_auth():
    with pytest.raises(Exception) as ei:
        link.raise_link_error(link.CODE_AUTH, "bad key")
    exc = ei.value
    assert exc.status_code == status.HTTP_502_BAD_GATEWAY
    assert exc.detail["code"] == link.CODE_AUTH


def test_raise_link_error_supports_ssh_codes():
    with pytest.raises(Exception) as ei:
        link.raise_link_error(link.CODE_SSH_UNREACHABLE, "ssh down")
    exc = ei.value
    assert exc.status_code == status.HTTP_502_BAD_GATEWAY
    assert exc.detail["code"] == link.CODE_SSH_UNREACHABLE
    assert exc.detail["hint"]


def test_classify_ssh_error_from_code_attr():
    class _Exc(Exception):
        code = link.CODE_SSH_AUTH

    code, message = link.classify_ssh_error(_Exc("bad key")) or ("", "")
    assert code == link.CODE_SSH_AUTH
    assert "bad key" in message
