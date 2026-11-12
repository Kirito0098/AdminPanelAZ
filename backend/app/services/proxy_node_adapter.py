"""HTTP client for panel ↔ proxy_agent (port 9101 by default).

Uses the shared ``node_agent_request`` transport from ``node_adapter``; does not
implement NodeAdapter (VPN ops). Use ``get_proxy_adapter(node)`` from node_manager.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services.node_mtls import (
    build_node_agent_ssl_context,
    node_agent_base_scheme,
)

HTTP_TIMEOUT = 30.0


class ProxyNodeAdapter:
    """Thin client for proxy_agent health / status / destination / mappings."""

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        *,
        mtls_enabled: bool = False,
    ):
        self._mtls_enabled = mtls_enabled
        scheme = node_agent_base_scheme(mtls_enabled=mtls_enabled)
        self.base_url = f"{scheme}://{host}:{port}"
        self.api_key = api_key
        self._verify = build_node_agent_ssl_context(mtls_enabled=mtls_enabled)

    def _get_http_client(self) -> httpx.Client:
        from app.services.node_adapter import shared_http_client

        return shared_http_client(
            self.base_url,
            self._mtls_enabled,
            self._verify,
            timeout=HTTP_TIMEOUT,
        )

    def close(self) -> None:
        """The client is shared per endpoint and closed at process shutdown."""

    def _headers(self) -> dict[str, str]:
        return {"X-Node-Key": self.api_key}

    def _request(self, method: str, path: str, **kwargs) -> Any:
        from app.services.node_adapter import node_agent_request

        timeout = kwargs.pop("timeout", HTTP_TIMEOUT)
        return node_agent_request(
            method,
            f"{self.base_url}{path}",
            client=self._get_http_client(),
            headers=self._headers(),
            timeout=timeout,
            mtls_enabled=self._mtls_enabled,
            agent_label="proxy_agent",
            **kwargs,
        )

    def health(self) -> dict[str, Any]:
        """GET /health → { ok, version }."""
        return self._request("GET", "/health", timeout=10.0)

    def proxy_status(self) -> dict[str, Any]:
        """GET /proxy/status → { installed, destination_ip, detail }."""
        return self._request("GET", "/proxy/status")

    def set_destination(self, ip: str) -> dict[str, Any]:
        """PUT /proxy/destination → updated status."""
        return self._request("PUT", "/proxy/destination", json={"destination_ip": ip})

    def mappings(self) -> dict[str, Any]:
        """GET /proxy/mappings → { mappings: [...] }."""
        return self._request("GET", "/proxy/mappings")
