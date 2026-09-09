"""Agent auth failures must not surface as panel session 401."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.node_adapter import RemoteNodeAdapter
from app.services.proxy_node_adapter import ProxyNodeAdapter


def _adapter_remote() -> RemoteNodeAdapter:
    return RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)


def _adapter_proxy() -> ProxyNodeAdapter:
    return ProxyNodeAdapter("10.0.0.9", 9101, "k" * 32, mtls_enabled=False)


def _mock_client(status_code: int, payload: dict | None = None, text: str = ""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text or ("" if payload is None else str(payload))
    response.content = b"x" if status_code != 204 else b""
    if payload is None:
        response.json.side_effect = ValueError("no json")
    else:
        response.json.return_value = payload
    client = MagicMock()
    client.request.return_value = response
    return client


def _auth_failure_payload(status_code: int) -> dict:
    if status_code == 401:
        return {"detail": "nope"}
    return {"detail": ""}


@pytest.mark.parametrize("status_code", [401, 403])
def test_remote_request_maps_agent_auth_to_502(status_code):
    adapter = _adapter_remote()
    adapter._get_http_client = MagicMock(
        return_value=_mock_client(status_code, _auth_failure_payload(status_code))
    )
    with pytest.raises(HTTPException) as exc:
        adapter._request("GET", "/health")
    assert exc.value.status_code == 502
    if status_code == 401:
        assert "X-Node-Key" in str(exc.value.detail)
    else:
        assert "NODE_AGENT_ALLOWED_IPS" in str(exc.value.detail) or "Доступ" in str(exc.value.detail)


@pytest.mark.parametrize("status_code", [401, 403])
def test_remote_request_bytes_maps_agent_auth_to_502(status_code):
    adapter = _adapter_remote()
    adapter._get_http_client = MagicMock(
        return_value=_mock_client(status_code, _auth_failure_payload(status_code))
    )
    with pytest.raises(HTTPException) as exc:
        adapter._request_bytes("GET", "/clients/openvpn/x/file")
    assert exc.value.status_code == 502
    if status_code == 401:
        assert "X-Node-Key" in str(exc.value.detail)
    else:
        assert "NODE_AGENT_ALLOWED_IPS" in str(exc.value.detail) or "Доступ" in str(exc.value.detail)


@pytest.mark.parametrize("status_code", [401, 403])
def test_proxy_request_maps_agent_auth_to_502(status_code):
    adapter = _adapter_proxy()
    adapter._get_http_client = MagicMock(
        return_value=_mock_client(status_code, _auth_failure_payload(status_code))
    )
    with pytest.raises(HTTPException) as exc:
        adapter._request("GET", "/health")
    assert exc.value.status_code == 502
    if status_code == 401:
        assert "X-Node-Key" in str(exc.value.detail)
    else:
        assert "allowlist" in str(exc.value.detail) or "Доступ" in str(exc.value.detail)


def test_remote_request_preserves_other_4xx():
    adapter = _adapter_remote()
    adapter._get_http_client = MagicMock(return_value=_mock_client(404, {"detail": "missing"}))
    with pytest.raises(HTTPException) as exc:
        adapter._request("GET", "/health")
    assert exc.value.status_code == 404
