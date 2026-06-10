from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.models import VpnType
from app.schemas import MonitoringService, OpenVpnClient, WireGuardPeer
from app.config import get_settings
from app.paths import get_cidr_list_dir
from app.services.node_mtls import build_node_agent_ssl_context, node_agent_base_scheme, node_agent_mtls_enabled
from app.services.node_mtls_certs import MtlsProvisionBundle
from app.services.antizapret import AntiZapretService
from app.services.antizapret_settings import read_antizapret_settings, update_antizapret_settings
from app.services.cidr.service import CidrRoutingService
from app.services.node_health import build_health_payload
from app.services.node_update import apply_node_update, check_agent_updates, resolve_repo_root
from app.services.openvpn_management import openvpn_management_service
from app.services.openvpn_ban_hook import ensure_openvpn_ban_check
from app.services.server_monitor import ServerMonitorService
from app.services.node_remote_cache import get_cached_monitoring_overview, monitoring_overview_cache_key
from app.services.wg_runtime import block_client_runtime, unblock_client_runtime

_settings = get_settings()

HTTP_TIMEOUT = 120.0


class NodeAdapter(ABC):
    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

    @abstractmethod
    def add_openvpn_client(self, client_name: str, cert_expire_days: int = 3650) -> str: ...

    @abstractmethod
    def delete_openvpn_client(self, client_name: str) -> str: ...

    @abstractmethod
    def list_openvpn_clients(self) -> list[str]: ...

    @abstractmethod
    def add_wireguard_client(self, client_name: str) -> str: ...

    @abstractmethod
    def delete_wireguard_client(self, client_name: str) -> str: ...

    @abstractmethod
    def list_wireguard_clients(self) -> list[str]: ...

    @abstractmethod
    def recreate_profiles(self) -> str: ...

    @abstractmethod
    def create_antizapret_backup(self) -> dict[str, str]: ...

    @abstractmethod
    def get_profile_files(self, client_name: str, vpn_type: VpnType) -> list[dict[str, str]]: ...

    def get_profile_files_batch(
        self,
        clients: list[tuple[str, VpnType]],
    ) -> dict[str, list[dict[str, str]]]:
        return {name: self.get_profile_files(name, vpn_type) for name, vpn_type in clients}

    @abstractmethod
    def read_profile_file(self, path: str) -> str: ...

    @abstractmethod
    def read_config_file(self, filename: str) -> str: ...

    @abstractmethod
    def write_config_file(self, filename: str, content: str) -> None: ...

    @abstractmethod
    def apply_config_changes(self) -> str: ...

    @abstractmethod
    def get_server_ip(self) -> str | None: ...

    @abstractmethod
    def get_service_status(self) -> list[MonitoringService]: ...

    @abstractmethod
    def parse_openvpn_status(self) -> list[OpenVpnClient]: ...

    @abstractmethod
    def get_openvpn_status_snapshot(self) -> tuple[list[OpenVpnClient], str]: ...

    @abstractmethod
    def get_openvpn_management_events(self) -> list[dict]: ...

    @abstractmethod
    def get_openvpn_socket_status(self) -> list[dict]: ...

    @abstractmethod
    def parse_wireguard_status(self) -> list[WireGuardPeer]: ...

    @abstractmethod
    def restart_service(self, service_name: str) -> str: ...

    @abstractmethod
    def get_routing_overview(self) -> dict: ...

    @abstractmethod
    def get_provider_content(self, filename: str) -> dict: ...

    @abstractmethod
    def save_provider_content(self, filename: str, content: str) -> dict: ...

    @abstractmethod
    def set_provider_enabled(self, filename: str, enabled: bool) -> dict: ...

    @abstractmethod
    def apply_cidr_preset(self, preset_key: str) -> dict: ...

    @abstractmethod
    def sync_cidr_providers(self) -> dict: ...

    @abstractmethod
    def read_route_file(self, file_key: str) -> dict: ...

    @abstractmethod
    def write_route_file(self, file_key: str, content: str) -> dict: ...

    @abstractmethod
    def get_route_result_files(self) -> dict: ...

    @abstractmethod
    def sync_game_routes_filter(
        self,
        *,
        include_game_keys: list[str] | None = None,
        exclude_game_keys: list[str] | None = None,
        include_game_domains: bool = True,
    ) -> dict: ...

    @abstractmethod
    def get_route_result_content(self, key: str) -> dict: ...

    @abstractmethod
    def get_antizapret_settings(self) -> dict[str, str]: ...

    @abstractmethod
    def update_antizapret_settings(self, updates: dict) -> dict: ...

    @abstractmethod
    def get_server_metrics(self, *, accurate_cpu: bool = False) -> dict: ...

    @abstractmethod
    def get_server_bandwidth(self, iface: str = "eth0", range_key: str = "1d") -> dict: ...

    @abstractmethod
    def list_server_interfaces(self) -> dict: ...

    @abstractmethod
    def block_wireguard_client_runtime(self, client_name: str) -> dict: ...

    @abstractmethod
    def unblock_wireguard_client_runtime(self, client_name: str) -> dict: ...

    @abstractmethod
    def disconnect_openvpn_client(self, client_name: str) -> dict: ...

    @abstractmethod
    def check_updates(self) -> dict[str, Any]: ...

    @abstractmethod
    def apply_update(self) -> dict[str, Any]: ...

    @abstractmethod
    def ensure_openvpn_ban_check(self) -> dict: ...


class LocalNodeAdapter(NodeAdapter):
    def __init__(self, service: AntiZapretService | None = None):
        self._service = service or AntiZapretService()
        self._cidr = CidrRoutingService(self._service.base_path, get_cidr_list_dir())
        self._monitor = ServerMonitorService()

    def health_check(self) -> dict[str, Any]:
        return build_health_payload(self._service)

    def add_openvpn_client(self, client_name: str, cert_expire_days: int = 3650) -> str:
        return self._service.add_openvpn_client(client_name, cert_expire_days)

    def delete_openvpn_client(self, client_name: str) -> str:
        return self._service.delete_openvpn_client(client_name)

    def list_openvpn_clients(self) -> list[str]:
        return self._service.list_openvpn_clients()

    def add_wireguard_client(self, client_name: str) -> str:
        return self._service.add_wireguard_client(client_name)

    def delete_wireguard_client(self, client_name: str) -> str:
        return self._service.delete_wireguard_client(client_name)

    def list_wireguard_clients(self) -> list[str]:
        return self._service.list_wireguard_clients()

    def recreate_profiles(self) -> str:
        return self._service.recreate_profiles()

    def create_antizapret_backup(self) -> dict[str, str]:
        return self._service.create_antizapret_backup()

    def get_profile_files(self, client_name: str, vpn_type: VpnType) -> list[dict[str, str]]:
        return self._service.get_profile_files(client_name, vpn_type)

    def read_profile_file(self, path: str) -> str:
        return self._service.read_profile_file(path)

    def read_config_file(self, filename: str) -> str:
        return self._service.read_config_file(filename)

    def write_config_file(self, filename: str, content: str) -> None:
        return self._service.write_config_file(filename, content)

    def apply_config_changes(self) -> str:
        return self._service.apply_config_changes()

    def get_server_ip(self) -> str | None:
        return self._service.get_server_ip()

    def get_service_status(self) -> list[MonitoringService]:
        return self._service.get_service_status()

    def parse_openvpn_status(self) -> list[OpenVpnClient]:
        clients, _ = self.get_openvpn_status_snapshot()
        return clients

    def get_openvpn_status_snapshot(self) -> tuple[list[OpenVpnClient], str]:
        return self._service.parse_openvpn_status()

    def get_openvpn_data_source(self) -> str:
        _, data_source = self.get_openvpn_status_snapshot()
        return data_source

    def get_openvpn_management_events(self) -> list[dict]:
        return openvpn_management_service.collect_events()

    def get_openvpn_socket_status(self) -> list[dict]:
        return openvpn_management_service.get_socket_status()

    def parse_wireguard_status(self) -> list[WireGuardPeer]:
        return self._service.parse_wireguard_status()

    def restart_service(self, service_name: str) -> str:
        return self._service.restart_service(service_name)

    def get_routing_overview(self) -> dict:
        return self._cidr.get_overview()

    def get_provider_content(self, filename: str) -> dict:
        return self._cidr.get_provider_content(filename)

    def save_provider_content(self, filename: str, content: str) -> dict:
        return self._cidr.save_provider_content(filename, content)

    def set_provider_enabled(self, filename: str, enabled: bool) -> dict:
        return self._cidr.set_provider_enabled(filename, enabled)

    def apply_cidr_preset(self, preset_key: str) -> dict:
        return self._cidr.apply_preset(preset_key)

    def sync_cidr_providers(self) -> dict:
        return self._cidr.sync_providers()

    def read_route_file(self, file_key: str) -> dict:
        return self._cidr.read_route_file(file_key)

    def write_route_file(self, file_key: str, content: str) -> dict:
        return self._cidr.write_route_file(file_key, content)

    def sync_game_routes_filter(
        self,
        *,
        include_game_keys: list[str] | None = None,
        exclude_game_keys: list[str] | None = None,
        include_game_domains: bool = True,
    ) -> dict:
        from app.services.cidr.game_filter_sync import run_sync_game_routes_filter

        return run_sync_game_routes_filter(
            self._service.config_dir,
            include_game_keys=include_game_keys,
            exclude_game_keys=exclude_game_keys,
            include_game_domains=include_game_domains,
        )

    def get_route_result_files(self) -> dict:
        return self._cidr.get_result_files()

    def get_route_result_content(self, key: str) -> dict:
        return self._cidr.get_result_content(key)

    def get_antizapret_settings(self) -> dict[str, str]:
        return read_antizapret_settings(self._service.base_path / "setup")

    def update_antizapret_settings(self, updates: dict) -> dict:
        return update_antizapret_settings(self._service.base_path / "setup", updates)

    def get_server_metrics(self, *, accurate_cpu: bool = False) -> dict:
        return self._monitor.get_metrics(accurate_cpu=accurate_cpu)

    def get_server_bandwidth(self, iface: str = "eth0", range_key: str = "1d") -> dict:
        return self._monitor.get_bandwidth(iface, range_key)

    def list_server_interfaces(self) -> dict:
        return self._monitor.list_interfaces()

    def block_wireguard_client_runtime(self, client_name: str) -> dict:
        return block_client_runtime(client_name)

    def unblock_wireguard_client_runtime(self, client_name: str) -> dict:
        return unblock_client_runtime(client_name)

    def disconnect_openvpn_client(self, client_name: str) -> dict:
        return openvpn_management_service.disconnect_client(client_name)

    def check_updates(self) -> dict[str, Any]:
        return check_agent_updates(repo_root=resolve_repo_root())

    def apply_update(self) -> dict[str, Any]:
        return apply_node_update(repo_root=resolve_repo_root())

    def ensure_openvpn_ban_check(self) -> dict:
        return ensure_openvpn_ban_check(self._service.base_path)


class RemoteNodeAdapter(NodeAdapter):
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
        self._overview_cache_key = monitoring_overview_cache_key(host, port)
        self._http_client: httpx.Client | None = None

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=HTTP_TIMEOUT, **self._client_kwargs())
        return self._http_client

    def close(self) -> None:
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _get_monitoring_overview(self) -> dict[str, Any]:
        ttl = max(0, int(_settings.monitoring_overview_cache_ttl_seconds))
        return get_cached_monitoring_overview(
            self._overview_cache_key,
            ttl,
            lambda: self._request("GET", "/monitoring/overview"),
        )

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
                    "Ошибка SSL (WRONG_VERSION_NUMBER): узел, вероятно, отвечает по HTTP, "
                    "а панель подключается по HTTPS. Отключите mTLS для узла или настройте "
                    "HTTPS на node agent."
                )
            return (
                "Ошибка SSL (WRONG_VERSION_NUMBER): узел, вероятно, отвечает по HTTPS (mTLS), "
                "а панель подключается по HTTP. Включите mTLS для узла на странице «Узлы»."
            )
        if "certificate verify failed" in msg or "certificate_verify_failed" in msg:
            return (
                "Ошибка проверки сертификата node agent. Проверьте CA и клиентский сертификат панели "
                "(NODE_AGENT_MTLS_CA_CERT, NODE_AGENT_MTLS_CLIENT_CERT, NODE_AGENT_MTLS_CLIENT_KEY) "
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
                "Node agent использует самоподписанный или неизвестный сертификат. "
                "Убедитесь, что CA панели совпадает с CA на узле (включите mTLS через панель)."
            )
        if "unknown ca" in msg or "tlsv1_alert_unknown_ca" in msg:
            return (
                "Node agent не доверяет клиентскому сертификату панели (unknown CA). "
                "Повторно включите mTLS для узла или проверьте NODE_AGENT_MTLS_CA_CERT на агенте."
            )
        if (
            "handshake failure" in msg
            or "sslv3_alert_handshake_failure" in msg
            or "alert handshake failure" in msg
        ):
            if self._mtls_enabled:
                return (
                    "Ошибка TLS handshake с node agent. Проверьте, что на узле включён mTLS, "
                    "сертификаты панели и агента выданы одним CA, и порт 9100 доступен с IP панели."
                )
            return (
                "Ошибка TLS handshake: узел, вероятно, ожидает mTLS. "
                "Включите mTLS для узла на странице «Узлы»."
            )
        if "ssl" in msg or "tls" in msg:
            if self._mtls_enabled:
                return (
                    "Ошибка SSL/mTLS при подключении к node agent. Проверьте сертификаты панели, "
                    "что узел отвечает по HTTPS и NODE_AGENT_ALLOWED_IPS не блокирует панель."
                )
            return (
                "Ошибка SSL при подключении по HTTP — узел, вероятно, отвечает по HTTPS (mTLS). "
                "Включите mTLS для узла на странице «Узлы»."
            )
        return None

    def _format_connection_error(self, exc: httpx.RequestError) -> str:
        msg = str(exc).lower()
        if isinstance(exc, httpx.TimeoutException):
            return "Таймаут подключения к node agent — проверьте firewall и доступность порта"
        ssl_hint = self._format_ssl_error(msg)
        if ssl_hint is not None:
            return ssl_hint
        if isinstance(exc, httpx.ConnectError):
            return f"Не удалось подключиться к node agent: {exc}"
        if isinstance(exc, httpx.RemoteProtocolError) or "disconnected without sending a response" in msg:
            if not self._mtls_enabled:
                return (
                    "Сервер закрыл соединение без ответа. Вероятно, на узле включён mTLS (HTTPS), "
                    "а панель обращается по HTTP. Включите mTLS для узла на странице «Узлы» "
                    "или отключите mTLS на node agent."
                )
            return (
                "Сервер закрыл соединение без ответа. Проверьте mTLS-сертификаты панели "
                "(NODE_AGENT_MTLS_CA_CERT, NODE_AGENT_MTLS_CLIENT_CERT, NODE_AGENT_MTLS_CLIENT_KEY)."
            )
        return f"Узел недоступен: {exc}"

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
                detail = detail or "Доступ запрещён — проверьте NODE_AGENT_ALLOWED_IPS на узле"
            raise HTTPException(status_code=response.status_code, detail=detail)

        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def health_check(self) -> dict[str, Any]:
        return self._request("GET", "/health", timeout=10.0)

    def add_openvpn_client(self, client_name: str, cert_expire_days: int = 3650) -> str:
        data = self._request(
            "POST",
            "/clients/openvpn",
            json={"client_name": client_name, "cert_expire_days": cert_expire_days},
        )
        return data.get("message", "ok")

    def delete_openvpn_client(self, client_name: str) -> str:
        data = self._request("DELETE", f"/clients/openvpn/{client_name}")
        return data.get("message", "ok")

    def list_openvpn_clients(self) -> list[str]:
        data = self._request("GET", "/clients/openvpn")
        return data.get("clients", [])

    def add_wireguard_client(self, client_name: str) -> str:
        data = self._request("POST", "/clients/wireguard", json={"client_name": client_name})
        return data.get("message", "ok")

    def delete_wireguard_client(self, client_name: str) -> str:
        data = self._request("DELETE", f"/clients/wireguard/{client_name}")
        return data.get("message", "ok")

    def list_wireguard_clients(self) -> list[str]:
        data = self._request("GET", "/clients/wireguard")
        return data.get("clients", [])

    def recreate_profiles(self) -> str:
        data = self._request("POST", "/configs/recreate-profiles", timeout=300.0)
        return data.get("detail") or data.get("message", "ok")

    def create_antizapret_backup(self) -> dict[str, str]:
        data = self._request("POST", "/backups/antizapret", timeout=600.0)
        return {
            "archive_path": data.get("archive_path", ""),
            "archive_name": data.get("archive_name", ""),
        }

    def get_profile_files(self, client_name: str, vpn_type: VpnType) -> list[dict[str, str]]:
        data = self._request(
            "GET",
            "/profiles/files",
            params={"client_name": client_name, "vpn_type": vpn_type.value},
        )
        return data.get("files", [])

    def get_profile_files_batch(
        self,
        clients: list[tuple[str, VpnType]],
    ) -> dict[str, list[dict[str, str]]]:
        if not clients:
            return {}
        payload = {
            "clients": [
                {"client_name": name, "vpn_type": vpn_type.value}
                for name, vpn_type in clients
            ]
        }
        data = self._request("POST", "/profiles/files/batch", json=payload)
        raw = data.get("files_by_client", {})
        return {str(key): list(value or []) for key, value in raw.items()}

    def read_profile_file(self, path: str) -> str:
        data = self._request("GET", "/profiles/download", params={"path": path})
        return data.get("content", "")

    def read_config_file(self, filename: str) -> str:
        data = self._request("GET", f"/configs/files/{filename}")
        return data.get("content", "")

    def write_config_file(self, filename: str, content: str) -> None:
        self._request("PUT", f"/configs/files/{filename}", json={"content": content})

    def apply_config_changes(self) -> str:
        data = self._request("POST", "/configs/apply", timeout=300.0)
        return data.get("detail") or data.get("message", "ok")

    def get_server_ip(self) -> str | None:
        try:
            overview = self._get_monitoring_overview()
            ip = overview.get("server_ip")
            if ip:
                return str(ip)
        except Exception:
            pass
        data = self._request("GET", "/server/ip")
        return data.get("server_ip")

    def get_service_status(self) -> list[MonitoringService]:
        overview = self._get_monitoring_overview()
        return [MonitoringService(**s) for s in overview.get("services", [])]

    def parse_openvpn_status(self) -> list[OpenVpnClient]:
        clients, _ = self.get_openvpn_status_snapshot()
        return clients

    def get_openvpn_status_snapshot(self) -> tuple[list[OpenVpnClient], str]:
        overview = self._get_monitoring_overview()
        clients = [OpenVpnClient(**c) for c in overview.get("openvpn_clients", [])]
        return clients, overview.get("openvpn_data_source", "status_log")

    def get_openvpn_data_source(self) -> str:
        _, data_source = self.get_openvpn_status_snapshot()
        return data_source

    def get_openvpn_management_events(self) -> list[dict]:
        data = self._request("GET", "/openvpn/management/events")
        return data.get("profiles", [])

    def get_openvpn_socket_status(self) -> list[dict]:
        data = self._request("GET", "/openvpn/management/sockets")
        return data.get("sockets", [])

    def parse_wireguard_status(self) -> list[WireGuardPeer]:
        overview = self._get_monitoring_overview()
        return [WireGuardPeer(**p) for p in overview.get("wireguard_peers", [])]

    def restart_service(self, service_name: str) -> str:
        data = self._request("POST", "/services/restart", json={"service_name": service_name})
        return data.get("detail") or data.get("message", "ok")

    def get_routing_overview(self) -> dict:
        return self._request("GET", "/routing/overview")

    def get_provider_content(self, filename: str) -> dict:
        return self._request("GET", f"/routing/providers/{filename}")

    def save_provider_content(self, filename: str, content: str) -> dict:
        return self._request("PUT", f"/routing/providers/{filename}", json={"content": content})

    def set_provider_enabled(self, filename: str, enabled: bool) -> dict:
        return self._request("POST", f"/routing/providers/{filename}/enabled", json={"enabled": enabled})

    def apply_cidr_preset(self, preset_key: str) -> dict:
        return self._request("POST", f"/routing/presets/{preset_key}/apply")

    def sync_cidr_providers(self) -> dict:
        return self._request("POST", "/routing/sync")

    def read_route_file(self, file_key: str) -> dict:
        return self._request("GET", f"/routing/files/{file_key}")

    def write_route_file(self, file_key: str, content: str) -> dict:
        return self._request("PUT", f"/routing/files/{file_key}", json={"content": content})

    def sync_game_routes_filter(
        self,
        *,
        include_game_keys: list[str] | None = None,
        exclude_game_keys: list[str] | None = None,
        include_game_domains: bool = True,
    ) -> dict:
        from app.services.cidr.game_filter_sync import normalize_game_filter_sync_result

        data = self._request(
            "POST",
            "/routing/game-filters/sync",
            json={
                "include_game_keys": list(include_game_keys or []),
                "exclude_game_keys": list(exclude_game_keys or []),
                "include_game_domains": bool(include_game_domains),
            },
            timeout=300.0,
        )
        return normalize_game_filter_sync_result(data)

    def get_route_result_files(self) -> dict:
        return self._request("GET", "/routing/results")

    def get_route_result_content(self, key: str) -> dict:
        return self._request("GET", f"/routing/results/{key}")

    def get_antizapret_settings(self) -> dict[str, str]:
        data = self._request("GET", "/routing/antizapret-settings")
        return data.get("settings", {})

    def update_antizapret_settings(self, updates: dict) -> dict:
        return self._request("PUT", "/routing/antizapret-settings", json=updates)

    def get_server_metrics(self, *, accurate_cpu: bool = False) -> dict:
        return self._request(
            "GET",
            "/server-monitor/metrics",
            params={"accurate": "true" if accurate_cpu else "false"},
            timeout=30.0,
        )

    def get_server_bandwidth(self, iface: str = "eth0", range_key: str = "1d") -> dict:
        return self._request(
            "GET",
            "/server-monitor/bandwidth",
            params={"iface": iface, "range_key": range_key},
            timeout=30.0,
        )

    def list_server_interfaces(self) -> dict:
        return self._request("GET", "/server-monitor/interfaces", timeout=15.0)

    def block_wireguard_client_runtime(self, client_name: str) -> dict:
        return self._request("POST", f"/clients/wireguard/{client_name}/block", timeout=30.0)

    def unblock_wireguard_client_runtime(self, client_name: str) -> dict:
        return self._request("POST", f"/clients/wireguard/{client_name}/unblock", timeout=30.0)

    def disconnect_openvpn_client(self, client_name: str) -> dict:
        return self._request(
            "POST",
            "/openvpn/management/disconnect",
            json={"client_name": client_name},
            timeout=30.0,
        )

    def check_updates(self) -> dict[str, Any]:
        return self._request("GET", "/system/updates", timeout=60.0)

    def apply_update(self) -> dict[str, Any]:
        return self._request("POST", "/system/update", json={}, timeout=300.0)

    def ensure_openvpn_ban_check(self) -> dict:
        return self._request("POST", "/system/ensure-openvpn-ban-check", timeout=30.0)

    def rotate_api_key(self, new_api_key: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/system/rotate-api-key",
            json={"new_api_key": new_api_key},
            timeout=30.0,
        )

    @staticmethod
    def _is_agent_restart_disconnect(detail: object) -> bool:
        msg = str(detail).lower()
        return (
            "закрыл соединение без ответа" in msg
            or "disconnected without sending a response" in msg
        )

    def _provision_mtls_request(
        self,
        bundle: MtlsProvisionBundle,
        *,
        restart: bool,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/system/provision-mtls",
            json={
                "ca_pem": bundle.ca_pem,
                "agent_cert_pem": bundle.agent_cert_pem,
                "agent_key_pem": bundle.agent_key_pem,
                "restart": restart,
            },
            timeout=120.0,
        )

    def restart_agent_after_mtls(self) -> dict[str, Any]:
        return self._request("POST", "/system/restart-agent", json={}, timeout=30.0)

    def provision_mtls(self, bundle: MtlsProvisionBundle) -> dict[str, Any]:
        """Write mTLS materials on the node, then restart without dropping the HTTP response."""
        result = self._provision_mtls_request(bundle, restart=False)
        if not result.get("success"):
            return result

        restart_result: dict[str, Any] | None = None
        try:
            restart_result = self.restart_agent_after_mtls()
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                try:
                    self._provision_mtls_request(bundle, restart=True)
                    restart_result = {"method": "legacy", "success": True}
                except HTTPException as legacy_exc:
                    if not self._is_agent_restart_disconnect(legacy_exc.detail):
                        raise
                    restart_result = {"method": "legacy", "success": True}
            elif self._is_agent_restart_disconnect(exc.detail):
                restart_result = {"method": "in-request", "success": True}
            else:
                raise

        if restart_result is not None:
            result = {**result, "restart": restart_result}
        return result
