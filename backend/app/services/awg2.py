"""AZ-AWG2 (az-awg2 AmneziaWG 2.0 parallel layer) integration."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

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

_CLIENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


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


def _ensure_installed() -> None:
    if not is_awg2_installed():
        raise Awg2NotInstalledError(
            "AZ-AWG2 не установлен на узле. Установите: " + AWG2_INSTALL_CMD
        )


def _resolve_awg2_profile_path(path: str) -> Path:
    file_path = Path(path).resolve()
    client_root = AWG2_CLIENT_DIR.resolve()
    if not file_path.is_relative_to(client_root):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ к файлу запрещён")
    return file_path


def is_awg2_profile_path(path: str) -> bool:
    try:
        _resolve_awg2_profile_path(path)
        return True
    except HTTPException:
        return False


def _flock_prefix() -> list[str]:
    if Path("/usr/bin/flock").is_file() or Path("/bin/flock").is_file():
        return ["flock", "-w", "30", str(AWG2_CLIENT_LOCK)]
    return []


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
    def ensure_installed(self) -> None:
        _ensure_installed()

    def validate_client_name(self, name: str) -> str:
        value = (name or "").strip()
        if not _CLIENT_NAME_RE.match(value):
            raise ValueError("Некорректное имя клиента")
        return value

    def _run_awg_client(self, *args: str, timeout: int = 120) -> str:
        _ensure_installed()
        cmd = [*_flock_prefix(), str(AWG2_CLIENT_BIN), *args]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "awg-client failed").strip()
            raise RuntimeError(err)
        return (completed.stdout or "").strip()

    def add_client(self, name: str) -> str:
        name = self.validate_client_name(name)
        created: list[str] = []
        outputs: list[str] = []
        try:
            for tunnel in AWG2_TUNNELS:
                outputs.append(self._run_awg_client("add", name, tunnel))
                created.append(tunnel)
        except Exception:
            for tunnel in reversed(created):
                try:
                    self._run_awg_client("del", name, tunnel)
                except Exception:
                    pass
            raise
        return "\n".join(outputs)

    def delete_client(self, name: str) -> str:
        name = self.validate_client_name(name)
        outputs: list[str] = []
        for tunnel in AWG2_TUNNELS:
            conf = AWG2_CLIENT_DIR / tunnel / f"{tunnel}-{name}-am.conf"
            if not conf.is_file():
                continue
            try:
                outputs.append(self._run_awg_client("del", name, tunnel))
            except RuntimeError as exc:
                msg = str(exc).lower()
                if (
                    "не существует" in msg
                    or "not found" in msg
                    or "не найден" in msg
                ):
                    continue
                raise
        return "\n".join(outputs) or f"Клиент '{name}' удалён (файлов не было)"

    def get_profile_files(self, client_name: str) -> list[dict[str, str]]:
        name = self.validate_client_name(client_name)
        files: list[dict[str, str]] = []
        for tunnel in AWG2_TUNNELS:
            path = AWG2_CLIENT_DIR / tunnel / f"{tunnel}-{name}-am.conf"
            if path.is_file():
                files.append(
                    {
                        "protocol": "amneziawg2",
                        "variant": tunnel,
                        "path": str(path),
                        "filename": path.name,
                    }
                )
            for extra_suffix, kind in (
                (".vpn", "vpnuri"),
                ("-vpnuri.txt", "vpnuri"),
            ):
                extra = AWG2_CLIENT_DIR / tunnel / f"{tunnel}-{name}{extra_suffix}"
                if extra.is_file():
                    files.append(
                        {
                            "protocol": "amneziawg2",
                            "variant": tunnel,
                            "path": str(extra),
                            "filename": extra.name,
                            "kind": kind,
                        }
                    )
        return files

    def read_profile_file(self, path: str) -> str:
        file_path = _resolve_awg2_profile_path(path)
        if not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
        return file_path.read_text(encoding="utf-8", errors="replace")

    def write_profile_file(self, path: str, content: str) -> None:
        file_path = _resolve_awg2_profile_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content or "", encoding="utf-8")

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

    def list_all_client_names(self) -> list[str]:
        names = set(self.list_clients("antizapret")) | set(self.list_clients("vpn"))
        return sorted(names)
