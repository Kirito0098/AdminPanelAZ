"""AZ-AWG2 (az-awg2 AmneziaWG 2.0 parallel layer) integration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

AWG2_CLIENT_BIN = Path(os.environ.get("AWG2_CLIENT_BIN", "/usr/local/bin/awg-client"))
AWG2_OVERLAY_DIR = Path(os.environ.get("AWG2_OVERLAY_DIR", "/opt/antizapret-awg"))
AWG2_AMNEZIA_DIR = Path(os.environ.get("AWG2_AMNEZIA_DIR", "/etc/amnezia/amneziawg"))
AWG2_CLIENT_DIR = AWG2_OVERLAY_DIR / "clients"
AWG2_SERVICES_ENV = AWG2_AMNEZIA_DIR / "services.env"
AWG2_CLIENT_LOCK = Path(os.environ.get("AWG2_CLIENT_LOCK", "/run/antizapret-awg-client.lock"))
AWG2_TUNNELS = ("antizapret", "vpn")

AWG2_INSTALL_CMD = (
    "bash <(curl -fsSL https://raw.githubusercontent.com/blindtechnique/az-awg2/main/install.sh)"
)
AWG2_UPDATE_CMD = (
    "bash <(curl -fsSL https://raw.githubusercontent.com/blindtechnique/az-awg2/main/install.sh) --update"
)


class Awg2NotInstalledError(Exception):
    """az-awg2 layer is not installed on this node."""


def detect_awg2_installation() -> dict[str, Any]:
    bin_ok = AWG2_CLIENT_BIN.is_file() and os.access(AWG2_CLIENT_BIN, os.X_OK)
    overlay_ok = AWG2_OVERLAY_DIR.is_dir()
    amnezia_ok = AWG2_AMNEZIA_DIR.is_dir()
    missing: list[str] = []
    if not bin_ok:
        missing.append("awg_client")
    if not overlay_ok:
        missing.append("overlay_dir")
    if not amnezia_ok:
        missing.append("amnezia_dir")
    return {
        "installed": bin_ok and overlay_ok and amnezia_ok,
        "awg_client": bin_ok,
        "overlay_dir": overlay_ok,
        "amnezia_dir": amnezia_ok,
        "missing_components": missing,
    }


def is_awg2_installed() -> bool:
    return bool(detect_awg2_installation()["installed"])


def _read_services_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if not AWG2_SERVICES_ENV.is_file():
        return data
    for line in AWG2_SERVICES_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


class Awg2Service:
    def get_health(self) -> dict[str, Any]:
        detected = detect_awg2_installation()
        return {
            **detected,
            "install_command": AWG2_INSTALL_CMD,
            "update_command": AWG2_UPDATE_CMD,
        }

    def get_status(self) -> dict[str, Any]:
        if not is_awg2_installed():
            raise Awg2NotInstalledError(
                "AZ-AWG2 не установлен на узле. Установите: " + AWG2_INSTALL_CMD
            )
        env = _read_services_env()
        return {
            "installed": True,
            "services_env": {
                "AZ_IFACE": env.get("AZ_IFACE"),
                "VPN_IFACE": env.get("VPN_IFACE"),
                "AZ_PORT": env.get("AZ_PORT"),
                "VPN_PORT": env.get("VPN_PORT"),
                "AZ_SUBNET": env.get("AZ_SUBNET"),
                "VPN_SUBNET": env.get("VPN_SUBNET"),
            },
            "client_counts": {
                "antizapret": len(self.list_clients("antizapret")),
                "vpn": len(self.list_clients("vpn")),
            },
        }

    def list_clients(self, tunnel: str = "antizapret") -> list[str]:
        if tunnel not in AWG2_TUNNELS:
            raise ValueError(f"unknown tunnel: {tunnel}")
        directory = AWG2_CLIENT_DIR / tunnel
        if not directory.is_dir():
            return []
        names: list[str] = []
        prefix = f"{tunnel}-"
        suffix = "-am.conf"
        for path in sorted(directory.glob(f"{prefix}*-am.conf")):
            stem = path.name
            if stem.startswith(prefix) and stem.endswith(suffix):
                names.append(stem[len(prefix) : -len(suffix)])
        return names
