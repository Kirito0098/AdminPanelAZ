"""Lightweight AntiZapret node agent — runs on each VPN server node."""

import os
import socket
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.models import VpnType
from app.config import get_settings
from app.services.antizapret import AntiZapretService
from app.services.cidr.service import CidrRoutingService
from app.services.openvpn_management import openvpn_management_service

NODE_AGENT_API_KEY = os.environ.get("NODE_AGENT_API_KEY", "change-me-node-agent-key")
ANTIZAPRET_PATH = Path(os.environ.get("ANTIZAPRET_PATH", "/root/antizapret"))
NODE_AGENT_PORT = int(os.environ.get("NODE_AGENT_PORT", "9100"))

_settings = get_settings()
service = AntiZapretService(base_path=ANTIZAPRET_PATH)
cidr_service = CidrRoutingService(ANTIZAPRET_PATH, _settings.cidr_list_dir)
app = FastAPI(title="AntiZapret Node Agent", version="1.0.0")


def verify_api_key(x_node_key: str = Header(..., alias="X-Node-Key")) -> None:
    if x_node_key != NODE_AGENT_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный API-ключ узла")


class ConfigContent(BaseModel):
    content: str = ""


class OpenVpnClientRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=32)
    cert_expire_days: int = Field(default=3650, ge=1, le=3650)


class WireGuardClientRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=32)


class ServiceRestartRequest(BaseModel):
    service_name: str


@app.get("/health")
def health(_: None = Depends(verify_api_key)):
    return {
        "status": "online",
        "hostname": socket.gethostname(),
        "antizapret_path": str(service.base_path),
        "server_ip": service.get_server_ip(),
        "timestamp": datetime.utcnow().isoformat(),
    }


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


@app.post("/services/restart")
def restart_service(payload: ServiceRestartRequest, _: None = Depends(verify_api_key)):
    output = service.restart_service(payload.service_name)
    return {"message": f"Служба {payload.service_name} перезапущена", "detail": output}


@app.get("/profiles/files")
def profile_files(client_name: str, vpn_type: str, _: None = Depends(verify_api_key)):
    vt = VpnType(vpn_type)
    return {"files": service.get_profile_files(client_name, vt)}


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=NODE_AGENT_PORT, reload=False)
