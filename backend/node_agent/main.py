"""Lightweight AntiZapret node agent — runs on each VPN server node."""

import ipaddress
import os
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from app.models import VpnType
from app.config import get_settings
from app.services.antizapret import AntiZapretService
from app.services.antizapret_settings import build_schema, filter_known_keys, read_antizapret_settings, update_antizapret_settings
from app.services.cidr.service import CidrRoutingService
from app.services.node_health import build_health_payload
from app.services.node_update import apply_node_update, check_all_updates, resolve_repo_root
from app.services.openvpn_management import openvpn_management_service
from app.services.openvpn_ban_hook import ensure_openvpn_ban_check
from app.services.server_monitor import ServerMonitorService
from app.services.wg_runtime import block_client_runtime, unblock_client_runtime

NODE_AGENT_API_KEY = os.environ.get("NODE_AGENT_API_KEY", "change-me-node-agent-key")
ANTIZAPRET_PATH = Path(os.environ.get("ANTIZAPRET_PATH", "/root/antizapret"))
NODE_AGENT_PORT = int(os.environ.get("NODE_AGENT_PORT", "9100"))
NODE_AGENT_MODE = os.environ.get("NODE_AGENT_MODE", "prod").strip().lower()
NODE_AGENT_ALLOWED_IPS = [
    ip.strip() for ip in os.environ.get("NODE_AGENT_ALLOWED_IPS", "").split(",") if ip.strip()
]
NODE_AGENT_MTLS_ENABLED = os.environ.get("NODE_AGENT_MTLS_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
}
NODE_AGENT_MTLS_SERVER_CERT = os.environ.get("NODE_AGENT_MTLS_SERVER_CERT", "/etc/adminpanelaz/mtls/agent.crt")
NODE_AGENT_MTLS_SERVER_KEY = os.environ.get("NODE_AGENT_MTLS_SERVER_KEY", "/etc/adminpanelaz/mtls/agent.key")
NODE_AGENT_MTLS_CA_CERT = os.environ.get("NODE_AGENT_MTLS_CA_CERT", "/etc/adminpanelaz/mtls/ca.crt")
NODE_AGENT_ENV_FILE = Path(os.environ.get("NODE_AGENT_ENV_FILE", "/etc/adminpanelaz/node_agent.env"))

from app.services.security_bootstrap import validate_node_agent_key

validate_node_agent_key(NODE_AGENT_API_KEY, production=NODE_AGENT_MODE == "prod")

_settings = get_settings()
service = AntiZapretService(base_path=ANTIZAPRET_PATH)
cidr_service = CidrRoutingService(ANTIZAPRET_PATH, _settings.cidr_list_dir)
monitor = ServerMonitorService()
app = FastAPI(title="AntiZapret Node Agent", version="1.1.0")


class NodeAgentIpAllowlistMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not NODE_AGENT_ALLOWED_IPS:
            return await call_next(request)
        client_ip = request.client.host if request.client else ""
        if client_ip.startswith("::ffff:"):
            client_ip = client_ip[7:]
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещён") from None
        for entry in NODE_AGENT_ALLOWED_IPS:
            try:
                if "/" in entry:
                    if addr in ipaddress.ip_network(entry, strict=False):
                        return await call_next(request)
                elif addr == ipaddress.ip_address(entry):
                    return await call_next(request)
            except ValueError:
                continue
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещён с вашего IP")


app.add_middleware(NodeAgentIpAllowlistMiddleware)


class NodeUpdateRequest(BaseModel):
    scope: str = Field(default="all", pattern="^(all|agent|antizapret)$")
    run_doall: bool = True


def verify_api_key(x_node_key: str = Header(..., alias="X-Node-Key")) -> None:
    if not x_node_key or not secrets.compare_digest(x_node_key, NODE_AGENT_API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный API-ключ узла")


class ConfigContent(BaseModel):
    content: str = ""


class OpenVpnClientRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=32)
    cert_expire_days: int = Field(default=3650, ge=1, le=3650)


class WireGuardClientRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=32)


class ProfileFilesClientRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=32)
    vpn_type: str


class ProfileFilesBatchRequest(BaseModel):
    clients: list[ProfileFilesClientRequest] = Field(default_factory=list)


class ServiceRestartRequest(BaseModel):
    service_name: str


class RotateApiKeyRequest(BaseModel):
    new_api_key: str = Field(min_length=24)


def _persist_api_key(new_key: str) -> None:
    global NODE_AGENT_API_KEY
    NODE_AGENT_API_KEY = new_key
    if not NODE_AGENT_ENV_FILE.is_file():
        return
    lines: list[str] = []
    replaced = False
    for line in NODE_AGENT_ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("NODE_AGENT_API_KEY="):
            lines.append(f"NODE_AGENT_API_KEY={new_key}")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        lines.append(f"NODE_AGENT_API_KEY={new_key}")
    NODE_AGENT_ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.get("/health")
def health(_: None = Depends(verify_api_key)):
    payload = build_health_payload(service, agent_version=app.version)
    payload["status"] = "online"
    payload["timestamp"] = datetime.utcnow().isoformat()
    return payload


@app.get("/server-monitor/metrics")
def server_metrics(accurate: bool = False, _: None = Depends(verify_api_key)):
    return monitor.get_metrics(accurate_cpu=accurate)


@app.get("/server-monitor/bandwidth")
def server_bandwidth(
    iface: str = "eth0",
    range_key: str = "1d",
    _: None = Depends(verify_api_key),
):
    return monitor.get_bandwidth(iface, range_key)


@app.get("/server-monitor/interfaces")
def server_interfaces(_: None = Depends(verify_api_key)):
    return monitor.list_interfaces()


@app.get("/monitoring/overview")
def monitoring_overview(_: None = Depends(verify_api_key)):
    ovpn_clients, openvpn_data_source = service.parse_openvpn_status()
    return {
        "services": [s.model_dump() for s in service.get_service_status()],
        "openvpn_clients": [c.model_dump() for c in ovpn_clients],
        "wireguard_peers": [p.model_dump() for p in service.parse_wireguard_status()],
        "server_ip": service.get_server_ip(),
        "timestamp": datetime.utcnow().isoformat(),
        "openvpn_data_source": openvpn_data_source,
    }


@app.get("/openvpn/management/events")
def openvpn_management_events(_: None = Depends(verify_api_key)):
    return {
        "profiles": openvpn_management_service.collect_events(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/openvpn/management/sockets")
def openvpn_management_sockets(_: None = Depends(verify_api_key)):
    return {
        "sockets": openvpn_management_service.get_socket_status(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/server/ip")
def server_ip(_: None = Depends(verify_api_key)):
    return {"server_ip": service.get_server_ip()}


@app.post("/openvpn/management/disconnect")
def openvpn_disconnect(payload: WireGuardClientRequest, _: None = Depends(verify_api_key)):
    return openvpn_management_service.disconnect_client(payload.client_name)


@app.get("/clients/openvpn")
def list_openvpn(_: None = Depends(verify_api_key)):
    return {"clients": service.list_openvpn_clients()}


@app.post("/clients/openvpn")
def add_openvpn(payload: OpenVpnClientRequest, _: None = Depends(verify_api_key)):
    output = service.add_openvpn_client(payload.client_name, payload.cert_expire_days)
    return {"message": "OpenVPN клиент создан", "detail": output}


@app.delete("/clients/openvpn/{client_name}")
def delete_openvpn(client_name: str, _: None = Depends(verify_api_key)):
    output = service.delete_openvpn_client(client_name)
    return {"message": f"Клиент '{client_name}' удалён", "detail": output}


@app.get("/clients/wireguard")
def list_wireguard(_: None = Depends(verify_api_key)):
    return {"clients": service.list_wireguard_clients()}


@app.post("/clients/wireguard")
def add_wireguard(payload: WireGuardClientRequest, _: None = Depends(verify_api_key)):
    output = service.add_wireguard_client(payload.client_name)
    return {"message": "WireGuard клиент создан", "detail": output}


@app.delete("/clients/wireguard/{client_name}")
def delete_wireguard(client_name: str, _: None = Depends(verify_api_key)):
    output = service.delete_wireguard_client(client_name)
    return {"message": f"Клиент '{client_name}' удалён", "detail": output}


@app.post("/clients/wireguard/{client_name}/block")
def block_wireguard(client_name: str, _: None = Depends(verify_api_key)):
    return block_client_runtime(client_name)


@app.post("/clients/wireguard/{client_name}/unblock")
def unblock_wireguard(client_name: str, _: None = Depends(verify_api_key)):
    return unblock_client_runtime(client_name)


@app.get("/configs/files/{filename}")
def read_config(filename: str, _: None = Depends(verify_api_key)):
    return {"content": service.read_config_file(filename)}


@app.put("/configs/files/{filename}")
def write_config(filename: str, payload: ConfigContent, _: None = Depends(verify_api_key)):
    service.write_config_file(filename, payload.content)
    return {"message": f"Файл {filename} сохранён"}


@app.post("/configs/apply")
def apply_config(_: None = Depends(verify_api_key)):
    output = service.apply_config_changes()
    return {"message": "Настройки применены", "detail": output}


@app.post("/configs/recreate-profiles")
def recreate_profiles(_: None = Depends(verify_api_key)):
    output = service.recreate_profiles()
    return {"message": "Профили пересозданы", "detail": output}


@app.post("/backups/antizapret")
def create_antizapret_backup(_: None = Depends(verify_api_key)):
    result = service.create_antizapret_backup()
    return {
        "message": "Бэкап AntiZapret создан",
        **result,
    }


@app.post("/services/restart")
def restart_service(payload: ServiceRestartRequest, _: None = Depends(verify_api_key)):
    output = service.restart_service(payload.service_name)
    return {"message": f"Служба {payload.service_name} перезапущена", "detail": output}


@app.get("/profiles/files")
def profile_files(client_name: str, vpn_type: str, _: None = Depends(verify_api_key)):
    vt = VpnType(vpn_type)
    return {"files": service.get_profile_files(client_name, vt)}


@app.post("/profiles/files/batch")
def profile_files_batch(payload: ProfileFilesBatchRequest, _: None = Depends(verify_api_key)):
    files_by_client: dict[str, list] = {}
    for item in payload.clients:
        try:
            vt = VpnType(item.vpn_type)
        except ValueError:
            files_by_client[item.client_name] = []
            continue
        files_by_client[item.client_name] = service.get_profile_files(item.client_name, vt)
    return {"files_by_client": files_by_client}


@app.get("/profiles/download")
def profile_download(path: str, _: None = Depends(verify_api_key)):
    return {"content": service.read_profile_file(path)}


@app.get("/routing/overview")
def routing_overview(_: None = Depends(verify_api_key)):
    return cidr_service.get_overview()


@app.get("/routing/providers/{filename}")
def routing_provider_get(filename: str, _: None = Depends(verify_api_key)):
    return cidr_service.get_provider_content(filename)


@app.put("/routing/providers/{filename}")
def routing_provider_put(filename: str, payload: ConfigContent, _: None = Depends(verify_api_key)):
    return cidr_service.save_provider_content(filename, payload.content)


@app.post("/routing/providers/{filename}/enabled")
def routing_provider_enabled(filename: str, payload: dict, _: None = Depends(verify_api_key)):
    return cidr_service.set_provider_enabled(filename, bool(payload.get("enabled", False)))


@app.post("/routing/presets/{preset_key}/apply")
def routing_preset_apply(preset_key: str, _: None = Depends(verify_api_key)):
    return cidr_service.apply_preset(preset_key)


@app.post("/routing/sync")
def routing_sync(_: None = Depends(verify_api_key)):
    return cidr_service.sync_providers()


class GameFiltersSyncRequest(BaseModel):
    include_game_keys: list[str] = Field(default_factory=list)
    exclude_game_keys: list[str] = Field(default_factory=list)
    include_game_domains: bool = True


@app.post("/routing/game-filters/sync")
def routing_game_filters_sync(payload: GameFiltersSyncRequest, _: None = Depends(verify_api_key)):
    from app.services.cidr.game_filter_sync import run_sync_game_routes_filter

    result = run_sync_game_routes_filter(
        service.config_dir,
        include_game_keys=payload.include_game_keys,
        exclude_game_keys=payload.exclude_game_keys,
        include_game_domains=payload.include_game_domains,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message") or "Game filter sync failed")
    return result


@app.get("/routing/files/{file_key}")
def routing_file_get(file_key: str, _: None = Depends(verify_api_key)):
    return cidr_service.read_route_file(file_key)


@app.put("/routing/files/{file_key}")
def routing_file_put(file_key: str, payload: ConfigContent, _: None = Depends(verify_api_key)):
    return cidr_service.write_route_file(file_key, payload.content)


@app.get("/routing/results")
def routing_results(_: None = Depends(verify_api_key)):
    return cidr_service.get_result_files()


@app.get("/routing/results/{key}")
def routing_result_content(key: str, _: None = Depends(verify_api_key)):
    return cidr_service.get_result_content(key)


@app.get("/routing/antizapret-settings")
def routing_antizapret_settings_get(_: None = Depends(verify_api_key)):
    settings_data = read_antizapret_settings(ANTIZAPRET_PATH / "setup")
    return {"settings": settings_data, "schema": build_schema()}


@app.put("/routing/antizapret-settings")
def routing_antizapret_settings_put(payload: dict, _: None = Depends(verify_api_key)):
    try:
        return update_antizapret_settings(ANTIZAPRET_PATH / "setup", filter_known_keys(payload))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет прав на запись") from exc


@app.get("/system/updates")
def system_updates(_: None = Depends(verify_api_key)):
    return check_all_updates(antizapret_path=ANTIZAPRET_PATH, repo_root=resolve_repo_root())


@app.post("/system/ensure-openvpn-ban-check")
def system_ensure_openvpn_ban_check(_: None = Depends(verify_api_key)):
    return ensure_openvpn_ban_check(ANTIZAPRET_PATH)


@app.post("/system/rotate-api-key")
def rotate_api_key(payload: RotateApiKeyRequest, _: None = Depends(verify_api_key)):
    _persist_api_key(payload.new_api_key)
    return {"message": "API-ключ обновлён", "success": True}


@app.post("/system/update")
def system_update(payload: NodeUpdateRequest, _: None = Depends(verify_api_key)):
    result = apply_node_update(
        antizapret_path=ANTIZAPRET_PATH,
        service=service,
        scope=payload.scope,
        run_doall=payload.run_doall,
        agent_version=app.version,
        repo_root=resolve_repo_root(),
    )
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="; ".join(result.get("errors") or [result.get("message", "Ошибка обновления")]),
        )
    return result


def _uvicorn_ssl_kwargs() -> dict:
    if not NODE_AGENT_MTLS_ENABLED:
        return {}
    cert = Path(NODE_AGENT_MTLS_SERVER_CERT)
    key = Path(NODE_AGENT_MTLS_SERVER_KEY)
    ca = Path(NODE_AGENT_MTLS_CA_CERT)
    if not all(p.is_file() for p in (cert, key, ca)):
        return {}
    return {
        "ssl_certfile": str(cert),
        "ssl_keyfile": str(key),
        "ssl_ca_certs": str(ca),
        "ssl_cert_reqs": 2,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=NODE_AGENT_PORT,
        reload=False,
        **_uvicorn_ssl_kwargs(),
    )
