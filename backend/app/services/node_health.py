"""Shared node health payload for local adapter and node agent."""

from __future__ import annotations

import platform
import socket
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.antizapret import AntiZapretService

HEALTH_METADATA_KEYS = (
    "hostname",
    "antizapret_path",
    "antizapret_version",
    "server_ip",
    "services_active",
    "services_total",
    "os",
    "agent_version",
    "started_at",
    "uptime_sec",
    "listen_tls",
)

# Keep in sync with node agent HTTP API; shared by local adapter and node_agent/main.py.
NODE_AGENT_VERSION = "1.8.0"

_PROCESS_STARTED_AT = datetime.now(timezone.utc)


def build_health_payload(
    service: AntiZapretService,
    *,
    agent_version: str = NODE_AGENT_VERSION,
    listen_tls: bool | None = None,
) -> dict:
    services = service.get_service_status()
    active_count = sum(1 for s in services if s.active)
    now = datetime.now(timezone.utc)
    payload: dict = {
        "hostname": socket.gethostname(),
        "antizapret_path": str(service.base_path),
        "antizapret_version": service.get_antizapret_version(),
        "server_ip": service.get_server_ip(),
        "services_active": active_count,
        "services_total": len(services),
        "os": platform.system(),
        "agent_version": agent_version,
        "started_at": _PROCESS_STARTED_AT.isoformat().replace("+00:00", "Z"),
        "uptime_sec": max(0, int((now - _PROCESS_STARTED_AT).total_seconds())),
    }
    if listen_tls is not None:
        payload["listen_tls"] = bool(listen_tls)
    return payload
