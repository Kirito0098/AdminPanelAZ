"""Shared node health payload for local adapter and node agent."""

from __future__ import annotations

import platform
import socket
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
)


def build_health_payload(service: AntiZapretService, *, agent_version: str = "1.0.0") -> dict:
    services = service.get_service_status()
    active_count = sum(1 for s in services if s.active)
    return {
        "hostname": socket.gethostname(),
        "antizapret_path": str(service.base_path),
        "antizapret_version": service.get_antizapret_version(),
        "server_ip": service.get_server_ip(),
        "services_active": active_count,
        "services_total": len(services),
        "os": platform.system(),
        "agent_version": agent_version,
    }
