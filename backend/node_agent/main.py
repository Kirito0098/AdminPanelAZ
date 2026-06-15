"""Lightweight AntiZapret node agent — runs on each VPN server node."""

import ipaddress
import os
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from app.models import VpnType
from app.paths import get_cidr_list_dir
from app.services.antizapret import AntiZapretService
from app.services.antizapret_settings import build_schema, filter_known_keys, read_antizapret_settings, update_antizapret_settings
from app.services.cidr.service import CidrRoutingService
from app.services.node_health import build_health_payload
from app.services.node_agent_provision import provision_mtls
from app.services.node_agent_env import resolve_node_agent_env_file
from app.services.node_update import (
    apply_node_update,
    check_agent_updates,
    resolve_repo_root,
    schedule_agent_restart,
)
from app.services.openvpn_management import openvpn_management_service
from app.services.openvpn_ban_hook import ensure_openvpn_ban_check
from app.services.profile_files import profile_files_batch_key
from app.services.server_monitor import ServerMonitorService
from app.services.wg_runtime import block_client_runtime, unblock_client_runtime
from app.services.warper import run_warper_action

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
NODE_AGENT_ENV_FILE = resolve_node_agent_env_file()

from app.services.security_bootstrap import validate_node_agent_key

validate_node_agent_key(NODE_AGENT_API_KEY, production=NODE_AGENT_MODE == "prod")

service = AntiZapretService(base_path=ANTIZAPRET_PATH)
cidr_service = CidrRoutingService(ANTIZAPRET_PATH, get_cidr_list_dir())
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
    pass


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


class ProvisionMtlsRequest(BaseModel):
    ca_pem: str = Field(min_length=64)
    agent_cert_pem: str = Field(min_length=64)
    agent_key_pem: str = Field(min_length=64)
    restart: bool = True


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


@app.get("/backups/antizapret/download")
def download_antizapret_backup(
    name: str = Query(..., min_length=1),
    _: None = Depends(verify_api_key),
):
    candidate = Path(name)
    if not candidate.is_file():
        candidate = ANTIZAPRET_PATH / name
    if not candidate.is_file():
        candidate = Path("/root") / name
    if not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Архив не найден")
    return FileResponse(candidate, filename=candidate.name, media_type="application/gzip")


@app.post("/backups/antizapret/restore")
async def restore_antizapret_backup(
    archive: UploadFile = File(...),
    _: None = Depends(verify_api_key),
):
    import tempfile

    suffix = ".tar.gz"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await archive.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = service.restore_antizapret_backup(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return {
        "message": "AntiZapret восстановлен из бэкапа",
        **result,
    }


@app.get("/backups/antizapret/fingerprints")
def antizapret_fingerprints(_: None = Depends(verify_api_key)):
    return {"fingerprints": service.get_antizapret_fingerprints()}


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
        key = profile_files_batch_key(item.client_name, item.vpn_type)
        try:
            vt = VpnType(item.vpn_type)
        except ValueError:
            files_by_client[key] = []
            continue
        files_by_client[key] = service.get_profile_files(item.client_name, vt)
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


@app.post("/routing/sync")
def routing_sync(_: None = Depends(verify_api_key)):
    return cidr_service.sync_providers()


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


class WarperDomainRequest(BaseModel):
    domain: str = Field(..., min_length=1)


class WarperDomainsBulkRequest(BaseModel):
    domains: list[str] = Field(default_factory=list)


class WarperDomainListRequest(BaseModel):
    enable: bool


class WarperIpRangeRequest(BaseModel):
    cidr: str = Field(..., min_length=1)


class WarperIpRangeModeRequest(BaseModel):
    mode: str = Field(..., min_length=1)


class WarperIpExportRequest(BaseModel):
    enable: bool


class WarperMtuRequest(BaseModel):
    mtu: int = Field(..., ge=1280, le=1500)


class WarperLogLevelRequest(BaseModel):
    level: str = Field(..., min_length=1)


@app.get("/warper/health")
def warper_health(_: None = Depends(verify_api_key)):
    return run_warper_action("health")


@app.get("/warper/status")
def warper_status(_: None = Depends(verify_api_key)):
    return run_warper_action("status")


@app.get("/warper/doctor")
def warper_doctor(_: None = Depends(verify_api_key)):
    return {"items": run_warper_action("doctor")}


@app.post("/warper/toggle")
def warper_toggle(_: None = Depends(verify_api_key)):
    return run_warper_action("toggle")


@app.get("/warper/domains")
def warper_domains_list(_: None = Depends(verify_api_key)):
    return {
        "domains": run_warper_action("list_domains"),
        "lists": run_warper_action("domain_lists_status"),
    }


@app.post("/warper/domains")
def warper_domains_add(payload: WarperDomainRequest, _: None = Depends(verify_api_key)):
    return run_warper_action("add_domain", domain=payload.domain)


@app.delete("/warper/domains/{domain:path}")
def warper_domains_remove(domain: str, _: None = Depends(verify_api_key)):
    return run_warper_action("remove_domain", domain=domain)


@app.post("/warper/domains/sync")
def warper_domains_sync(_: None = Depends(verify_api_key)):
    return run_warper_action("sync_domains")


@app.post("/warper/domains/bulk")
def warper_domains_bulk(payload: WarperDomainsBulkRequest, _: None = Depends(verify_api_key)):
    return run_warper_action("add_domains_bulk", domains=payload.domains)


@app.post("/warper/domains/lists/{name}")
def warper_domains_list_toggle(name: str, payload: WarperDomainListRequest, _: None = Depends(verify_api_key)):
    return run_warper_action("set_domain_list", name=name, enable=payload.enable)


@app.get("/warper/ip-ranges")
def warper_ip_ranges_list(_: None = Depends(verify_api_key)):
    return {"ranges": run_warper_action("list_ip_ranges")}


@app.post("/warper/ip-ranges")
def warper_ip_ranges_add(payload: WarperIpRangeRequest, _: None = Depends(verify_api_key)):
    return run_warper_action("add_ip_range", cidr=payload.cidr)


@app.delete("/warper/ip-ranges/{cidr:path}")
def warper_ip_ranges_remove(cidr: str, _: None = Depends(verify_api_key)):
    return run_warper_action("remove_ip_range", cidr=cidr)


@app.post("/warper/ip-ranges/sync")
def warper_ip_ranges_sync(_: None = Depends(verify_api_key)):
    return run_warper_action("sync_ip_ranges")


@app.post("/warper/ip-ranges/mode")
def warper_ip_ranges_mode(payload: WarperIpRangeModeRequest, _: None = Depends(verify_api_key)):
    return run_warper_action("set_ip_route_mode", mode=payload.mode)


@app.post("/warper/ip-ranges/export")
def warper_ip_ranges_export(payload: WarperIpExportRequest, _: None = Depends(verify_api_key)):
    return run_warper_action("set_ip_export", enable=payload.enable)


@app.get("/warper/traffic")
def warper_traffic(period: str = "today", _: None = Depends(verify_api_key)):
    return run_warper_action("get_traffic", period=period)


@app.get("/warper/logs")
def warper_logs(lines: int = 200, _: None = Depends(verify_api_key)):
    return {"lines": run_warper_action("get_logs", lines=lines)}


@app.get("/warper/settings/mode")
def warper_settings_mode(_: None = Depends(verify_api_key)):
    return run_warper_action("get_mode")


@app.put("/warper/settings/mtu")
def warper_settings_mtu(payload: WarperMtuRequest, _: None = Depends(verify_api_key)):
    return run_warper_action("set_mtu", mtu=payload.mtu)


@app.put("/warper/settings/log-level")
def warper_settings_log_level(payload: WarperLogLevelRequest, _: None = Depends(verify_api_key)):
    return run_warper_action("set_log_level", level=payload.level)


@app.post("/warper/singbox/{action}")
def warper_singbox_action(action: str, _: None = Depends(verify_api_key)):
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Допустимо: start, stop, restart")
    return run_warper_action("singbox_action", action=action)


@app.get("/system/updates")
def system_updates(_: None = Depends(verify_api_key)):
    return check_agent_updates(repo_root=resolve_repo_root())


@app.post("/system/ensure-openvpn-ban-check")
def system_ensure_openvpn_ban_check(_: None = Depends(verify_api_key)):
    return ensure_openvpn_ban_check(ANTIZAPRET_PATH)


@app.post("/system/rotate-api-key")
def rotate_api_key(payload: RotateApiKeyRequest, _: None = Depends(verify_api_key)):
    _persist_api_key(payload.new_api_key)
    return {"message": "API-ключ обновлён", "success": True}


@app.post("/system/restart-agent")
def system_restart_agent(_: None = Depends(verify_api_key)):
    repo_root = resolve_repo_root()
    if repo_root is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Репозиторий node agent не найден для перезапуска",
        )
    schedule_agent_restart(repo_root)
    return {
        "success": True,
        "message": "Перезапуск node agent запланирован",
        "restarting": True,
    }


@app.post("/system/provision-mtls")
def system_provision_mtls(payload: ProvisionMtlsRequest, _: None = Depends(verify_api_key)):
    try:
        result = provision_mtls(
            ca_pem=payload.ca_pem,
            agent_cert_pem=payload.agent_cert_pem,
            agent_key_pem=payload.agent_key_pem,
            restart=payload.restart,
            repo_root=resolve_repo_root(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "Ошибка provision mTLS"),
        )
    return result


@app.post("/system/update")
def system_update(_payload: NodeUpdateRequest, _: None = Depends(verify_api_key)):
    result = apply_node_update(
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
