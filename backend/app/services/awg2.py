"""AZ-AWG2 (az-awg2 AmneziaWG 2.0 parallel layer) integration."""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
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


class Awg2ReplicaNotInstalledError(Awg2NotInstalledError):
    """AZ-AWG2 replica is not installed enough for HA sync operations."""

    def __init__(self, message: str, *, install_command: str):
        super().__init__(message)
        self.install_command = install_command


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


def _ensure_replica_installed() -> None:
    missing: list[str] = []
    if not AWG2_CLIENT_BIN.is_file():
        missing.append("awg_client")
    if not AWG2_OVERLAY_DIR.is_dir():
        missing.append("overlay_dir")
    if not AWG2_AMNEZIA_DIR.is_dir():
        missing.append("amnezia_dir")
    if missing:
        raise Awg2ReplicaNotInstalledError(
            f"AZ-AWG2 replica is not installed: missing {', '.join(missing)}",
            install_command=AWG2_INSTALL_CMD,
        )


def _is_excluded_archive_path(path: Path) -> bool:
    if path.name == "stats.db" or path.suffix == ".pyc":
        return True
    return any(part in {"venv", "__pycache__"} for part in path.parts)


def _write_tree_to_archive(archive: tarfile.TarFile, root: Path, archive_prefix: str) -> None:
    if not root.is_dir():
        return
    for item in sorted(root.rglob("*")):
        if not item.is_file() or _is_excluded_archive_path(item.relative_to(root)):
            continue
        archive.add(item, arcname=f"{archive_prefix}/{item.relative_to(root).as_posix()}")


def _replace_tree_from_snapshot(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        target.mkdir(parents=True, exist_ok=True)


def _tree_has_files(root: Path) -> bool:
    return root.is_dir() and any(item.is_file() for item in root.rglob("*"))


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

    def export_state_archive(self) -> bytes:
        _ensure_replica_installed()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            _write_tree_to_archive(archive, AWG2_AMNEZIA_DIR, "amneziawg")
            _write_tree_to_archive(archive, AWG2_CLIENT_DIR, "clients")
            manifest = "\n".join(
                [
                    "kind=az-awg2-state",
                    f"amnezia_dir={AWG2_AMNEZIA_DIR}",
                    f"client_dir={AWG2_CLIENT_DIR}",
                ]
            ).encode("utf-8")
            info = tarfile.TarInfo(name="MANIFEST")
            info.size = len(manifest)
            archive.addfile(info, io.BytesIO(manifest))
        return buffer.getvalue()

    def import_state_archive(self, data: bytes) -> None:
        if not data:
            raise ValueError("empty AWG2 archive")
        _ensure_replica_installed()

        with tempfile.TemporaryDirectory(prefix="awg2-import-") as temp_dir:
            temp_root = Path(temp_dir)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                archive.extractall(path=temp_root, filter="data")

            source_amnezia = temp_root / "amneziawg"
            source_clients = temp_root / "clients"
            if not _tree_has_files(source_amnezia) or not _tree_has_files(source_clients):
                raise ValueError(
                    "AWG2 archive must contain both amneziawg/ and clients/ files before import"
                )

            _replace_tree_from_snapshot(source_amnezia, AWG2_AMNEZIA_DIR)
            _replace_tree_from_snapshot(source_clients, AWG2_CLIENT_DIR)

    def apply_runtime(self) -> dict[str, Any]:
        _ensure_replica_installed()
        env = _read_services_env()
        interfaces = [
            iface.strip()
            for iface in (env.get("AZ_IFACE", ""), env.get("VPN_IFACE", ""))
            if iface and iface.strip()
        ]
        synced: list[str] = []
        restarted: list[str] = []
        errors: list[dict[str, str | None]] = []
        awg_bin = shutil.which("awg")

        if not interfaces:
            return {
                "success": False,
                "synced": synced,
                "restarted": restarted,
                "errors": [
                    {
                        "interface": None,
                        "stderr": "services.env does not define AZ_IFACE or VPN_IFACE",
                    }
                ],
            }

        for interface in interfaces:
            sync_error = "awg unavailable"
            if awg_bin:
                sync_error = self._sync_runtime_interface(interface)
                if sync_error is None:
                    synced.append(interface)
                    continue

            restart = subprocess.run(
                ["systemctl", "restart", f"awg-quick@{interface}"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if restart.returncode == 0:
                restarted.append(interface)
            else:
                errors.append(
                    {
                        "interface": interface,
                        "sync_error": sync_error,
                        "stderr": (restart.stderr or restart.stdout or "awg-quick restart failed").strip(),
                    }
                )

        return {
            "success": not errors,
            "synced": synced,
            "restarted": restarted,
            "errors": errors,
        }

    def _sync_runtime_interface(self, interface: str) -> str | None:
        strip_result = subprocess.run(
            ["awg-quick", "strip", interface],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if strip_result.returncode != 0:
            return (strip_result.stderr or strip_result.stdout or "awg-quick strip failed").strip()

        stripped_config = strip_result.stdout or ""
        if not stripped_config.strip():
            return "empty stripped config"

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as temp_file:
                temp_file.write(stripped_config)
                temp_path = temp_file.name
            sync_result = subprocess.run(
                ["awg", "syncconf", interface, temp_path],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if sync_result.returncode == 0:
                return None
            return (sync_result.stderr or sync_result.stdout or "awg syncconf failed").strip()
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
