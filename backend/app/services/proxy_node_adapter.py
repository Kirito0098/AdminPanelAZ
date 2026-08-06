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
        if "wrong version number" in msg or "wrong_version_number" in msg:
            if self._mtls_enabled:
                return (
                    "Ошибка SSL (WRONG_VERSION_NUMBER): proxy_agent, вероятно, отвечает по HTTP, "
                    "а панель подключается по HTTPS. Отключите mTLS для узла или настройте "
                    "HTTPS на proxy_agent."
                )
            return (
                "Ошибка SSL (WRONG_VERSION_NUMBER): proxy_agent, вероятно, отвечает по HTTPS (mTLS), "
                "а панель подключается по HTTP. Включите mTLS для узла на странице «Узлы»."
            )
        if "certificate verify failed" in msg or "certificate_verify_failed" in msg:
            return (
                "Ошибка проверки сертификата proxy_agent. Проверьте CA и клиентский сертификат панели "
                "или повторно включите mTLS для узла в панели."
            )
        if (
            "certificate has expired" in msg
            or "certificate expired" in msg
            or "certificate_expired" in msg
        ):
            return (
                "Сертификат mTLS истёк. Повторно включите mTLS для узла на странице «Узлы» "
                "или обновите сертификаты вручную."
            )
        if "self signed certificate" in msg or "self-signed certificate" in msg:
            return (
                "proxy_agent использует самоподписанный или неизвестный сертификат. "
                "Убедитесь, что CA панели совпадает с CA на узле."
            )
        if "unknown ca" in msg or "tlsv1_alert_unknown_ca" in msg:
            return (
                "proxy_agent не доверяет клиентскому сертификату панели (unknown CA). "
                "Повторно включите mTLS для узла или проверьте CA на агенте."
            )
        if (
            "handshake failure" in msg
            or "sslv3_alert_handshake_failure" in msg
            or "alert handshake failure" in msg
        ):
            if self._mtls_enabled:
                return (
                    "Ошибка TLS handshake с proxy_agent. Проверьте, что на узле включён mTLS, "
                    "сертификаты выданы одним CA, и порт доступен с IP панели."
                )
            return (
                "Ошибка TLS handshake: узел, вероятно, ожидает mTLS. "
                "Включите mTLS для узла на странице «Узлы»."
            )
        if "ssl" in msg or "tls" in msg:
            if self._mtls_enabled:
                return (
                    "Ошибка SSL/mTLS при подключении к proxy_agent. Проверьте сертификаты панели "
                    "и что узел отвечает по HTTPS."
                )
            return (
                "Ошибка SSL при подключении по HTTP — узел, вероятно, отвечает по HTTPS (mTLS). "
                "Включите mTLS для узла на странице «Узлы»."
            )
        return None

    def _format_connection_error(self, exc: httpx.RequestError) -> str:
        msg = str(exc).lower()
        if isinstance(exc, httpx.TimeoutException):
            return "Таймаут подключения к proxy_agent — проверьте firewall и доступность порта"
        ssl_hint = self._format_ssl_error(msg)
        if ssl_hint is not None:
            return ssl_hint
        if isinstance(exc, httpx.ConnectError):
            return f"Не удалось подключиться к proxy_agent: {exc}"
        if isinstance(exc, httpx.RemoteProtocolError) or "disconnected without sending a response" in msg:
            if not self._mtls_enabled:
                return (
                    "Сервер закрыл соединение без ответа. Вероятно, на узле включён mTLS (HTTPS), "
                    "а панель обращается по HTTP. Включите mTLS для узла на странице «Узлы»."
                )
            return (
                "Сервер закрыл соединение без ответа. Проверьте mTLS-сертификаты панели."
            )
        return f"Прокси-узел недоступен: {exc}"

    def _request(self, method: str, path: str, **kwargs) -> Any:
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
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=self._format_connection_error(exc),
            ) from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                data = response.json()
                detail = data.get("detail", detail)
            except Exception:
                pass
            if response.status_code == status.HTTP_401_UNAUTHORIZED:
                detail = "Неверный API-ключ узла (заголовок X-Node-Key)"
            elif response.status_code == status.HTTP_403_FORBIDDEN:
                detail = detail or "Доступ запрещён — проверьте allowlist IP на proxy_agent"
            raise HTTPException(status_code=response.status_code, detail=detail)

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
