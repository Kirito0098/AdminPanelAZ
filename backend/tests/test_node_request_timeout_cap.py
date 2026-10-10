"""A timeout cap shortens every agent request inside its context and nothing outside it."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.services import node_adapter
from app.services.node_adapter import HTTP_TIMEOUT, RemoteNodeAdapter, node_request_timeout_cap


def _adapter_with_client() -> tuple[RemoteNodeAdapter, MagicMock]:
    response = MagicMock()
    response.status_code = 200
    response.content = b"{}"
    response.json.return_value = {}
    client = MagicMock()
    client.request.return_value = response
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    adapter._get_http_client = MagicMock(return_value=client)
    return adapter, client


def _sent_timeout(client: MagicMock):
    return client.request.call_args.kwargs["timeout"]


def test_request_uses_default_timeout_without_cap():
    adapter, client = _adapter_with_client()

    adapter._request("GET", "/profiles/files")

    assert _sent_timeout(client) == HTTP_TIMEOUT


def test_cap_shortens_default_and_long_explicit_timeouts():
    adapter, client = _adapter_with_client()

    with node_request_timeout_cap(10.0):
        adapter._request("GET", "/profiles/files")
        default_timeout = _sent_timeout(client)
        adapter._request("POST", "/configs/apply", timeout=300.0)
        explicit_timeout = _sent_timeout(client)

    assert default_timeout == 10.0
    assert explicit_timeout == 10.0


def test_cap_keeps_shorter_explicit_timeout():
    adapter, client = _adapter_with_client()

    with node_request_timeout_cap(10.0):
        adapter._request("GET", "/health", timeout=5.0)

    assert _sent_timeout(client) == 5.0


def test_cap_applies_to_every_phase_of_httpx_timeout_in_request_bytes():
    adapter, client = _adapter_with_client()

    with node_request_timeout_cap(10.0):
        adapter._request_bytes("POST", "/backups/antizapret/restore", timeout=httpx.Timeout(660.0, connect=3.0))

    assert _sent_timeout(client) == httpx.Timeout(10.0, connect=3.0)


def test_cap_replaces_missing_timeout():
    with node_request_timeout_cap(10.0):
        assert node_adapter._effective_timeout(None) == 10.0


def test_cap_is_reset_after_context_even_on_error():
    with pytest.raises(RuntimeError):
        with node_request_timeout_cap(10.0):
            raise RuntimeError("boom")

    assert node_adapter._effective_timeout(HTTP_TIMEOUT) == HTTP_TIMEOUT
