"""HTTP client for panel ↔ proxy_agent (port 9101 by default).

Clones the RemoteNodeAdapter request/mTLS helpers; does not implement NodeAdapter
(VPN ops). Use ``get_proxy_adapter(node)`` from node_manager.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status

from app.services.node_mtls import (
    build_node_agent_ssl_context,
    node_agent_base_scheme,
    node_agent_mtls_enabled,
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
        mtls_enabled: bool | None = None,
    ):
        if mtls_enabled is None:
            mtls_enabled = node_agent_mtls_enabled()
        self._mtls_enabled = mtls_enabled
        scheme = node_agent_base_scheme(mtls_enabled=mtls_enabled)
        self.base_url = f"{scheme}://{host}:{port}"
        self.api_key = api_key
        self._verify = build_node_agent_ssl_context(mtls_enabled=mtls_enabled)
        self._http_client: httpx.Client | None = None

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=HTTP_TIMEOUT, **self._client_kwargs())
        return self._http_client

    def close(self) -> None:
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _headers(self) -> dict[str, str]:
        return {"X-Node-Key": self.api_key}

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self._verify is not None:
            kwargs["verify"] = self._verify
        return kwargs

    def _format_ssl_error(self, msg: str) -> str | None:
        from app.services.node_link_errors import _ssl_message

        # Prefer shared classifier wording; keep proxy-specific mTLS mark hint in TLS mismatch paths.
        base = _ssl_message(msg, mtls_enabled=self._mtls_enabled)
        if base is None:
            return None
        if "Включите mTLS для узла" in base:
            return (
                base.replace(
                    "Включите mTLS для узла на странице «Узлы».",
                    "Отметьте mTLS для прокси-узла на странице «Узлы» "
                    "(сертификаты proxy_agent — вручную, см. docs/proxy-agent.md).",
                )
            )
        return base.replace("node agent", "proxy_agent").replace("агенту узла", "proxy_agent")

    def _format_connection_error(self, exc: httpx.RequestError) -> str:
        from app.services.node_link_errors import classify_request_error

        _code, message = classify_request_error(exc, mtls_enabled=self._mtls_enabled)
        return message.replace("агенту узла", "proxy_agent").replace("агента узла", "proxy_agent")

    def _request(self, method: str, path: str, **kwargs) -> Any:
        from app.services.node_link_errors import (
            classify_http_status,
            classify_request_error,
            raise_link_error,
        )

        url = f"{self.base_url}{path}"
        timeout = kwargs.pop("timeout", HTTP_TIMEOUT)
        try:
            client = self._get_http_client()
            response = client.request(
                method,
                url,
                headers=self._headers(),
                timeout=timeout,
                **kwargs,
            )
        except httpx.RequestError as exc:
            code, message = classify_request_error(exc, mtls_enabled=self._mtls_enabled)
            raise_link_error(code, message)

        if response.status_code >= 400:
            detail = response.text
            try:
                data = response.json()
                detail = data.get("detail", detail)
            except Exception:
                pass
            code, message = classify_http_status(
                response.status_code, detail, mtls_enabled=self._mtls_enabled
            )
            raise_link_error(code, message)

        if response.status_code == 204 or not response.content:
            return None
        return response.json()


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
