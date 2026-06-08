import csv
import io
import re
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status

from app.config import get_settings
from app.models import VpnType
from app.schemas import MonitoringService, OpenVpnClient, WireGuardPeer
from app.services.antizapret_backup import AntizapretBackupService
from app.services.openvpn_management import openvpn_management_service

settings = get_settings()
CLIENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


class AntiZapretService:
    def __init__(self, base_path: Path | None = None):
        self.base_path = base_path or settings.antizapret_path
        self.client_script = self.base_path / "client.sh"
        self.client_dir = self.base_path / "client"
        self.config_dir = self.base_path / "config"
        self.openvpn_logs = Path("/etc/openvpn/server/logs")

    def _run_client_script(self, *args: str, timeout: int = 120) -> str:
        if not self.client_script.exists():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Скрипт AntiZapret не найден: {self.client_script}",
            )
        cmd = [str(self.client_script), *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Таймаут выполнения команды AntiZapret",
            ) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Ошибка запуска AntiZapret: {exc}",
            ) from exc

        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Ошибка AntiZapret: {output.strip() or 'неизвестная ошибка'}",
            )
        return output.strip()

    def validate_client_name(self, name: str) -> str:
        if not CLIENT_NAME_RE.match(name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Имя клиента: 1–32 символа (a-z, A-Z, 0-9, _, -)",
            )
        return name

    def add_openvpn_client(self, client_name: str, cert_expire_days: int = 3650) -> str:
        self.validate_client_name(client_name)
        return self._run_client_script("1", client_name, str(cert_expire_days))

    def delete_openvpn_client(self, client_name: str) -> str:
        self.validate_client_name(client_name)
        return self._run_client_script("2", client_name)

    def list_openvpn_clients(self) -> list[str]:
        output = self._run_client_script("3")
        clients: list[str] = []
        for line in output.splitlines():
            line = line.strip()
            if line and not line.startswith("OpenVPN") and line != "client names:":
                clients.append(line)
        return clients

    def add_wireguard_client(self, client_name: str) -> str:
        self.validate_client_name(client_name)
        return self._run_client_script("4", client_name)

    def delete_wireguard_client(self, client_name: str) -> str:
        self.validate_client_name(client_name)
        return self._run_client_script("5", client_name)

    def list_wireguard_clients(self) -> list[str]:
        output = self._run_client_script("6")
        clients: list[str] = []
        for line in output.splitlines():
            line = line.strip()
            if line and not line.startswith("WireGuard") and line != "client names:":
                clients.append(line)
        return clients

    def recreate_profiles(self) -> str:
        return self._run_client_script("7", timeout=300)

    def create_antizapret_backup(self) -> dict[str, str]:
        return AntizapretBackupService(install_dir=self.base_path).create_backup()

    def get_profile_files(self, client_name: str, vpn_type: VpnType) -> list[dict[str, str]]:
        files: list[dict[str, str]] = []
        if vpn_type == VpnType.openvpn:
            search_dirs = [
                ("openvpn", "antizapret", "antizapret", ".ovpn"),
                ("openvpn", "antizapret-udp", "antizapret-udp", "-udp.ovpn"),
                ("openvpn", "antizapret-tcp", "antizapret-tcp", "-tcp.ovpn"),
                ("openvpn", "vpn", "vpn", ".ovpn"),
                ("openvpn", "vpn-udp", "vpn-udp", "-udp.ovpn"),
                ("openvpn", "vpn-tcp", "vpn-tcp", "-tcp.ovpn"),
            ]
            prefix = "antizapret" if client_name.startswith("antizapret") else "vpn"
            for proto, variant, label, suffix in search_dirs:
                directory = self.client_dir / proto / variant
                if not directory.exists():
                    continue
                for path in directory.glob(f"*{client_name}*{suffix}"):
                    files.append({
                        "protocol": "openvpn",
                        "variant": label,
                        "filename": path.name,
                        "path": str(path),
                    })
                for path in directory.glob(f"{prefix}-*{suffix}"):
                    if client_name in path.name and not any(f["path"] == str(path) for f in files):
                        files.append({
                            "protocol": "openvpn",
                            "variant": label,
                            "filename": path.name,
                            "path": str(path),
                        })
        else:
            for proto, variant, suffix in [
                ("wireguard", "antizapret", "-wg.conf"),
                ("wireguard", "vpn", "-wg.conf"),
                ("amneziawg", "antizapret", "-am.conf"),
                ("amneziawg", "vpn", "-am.conf"),
            ]:
                directory = self.client_dir / proto / variant
                if not directory.exists():
                    continue
                for path in directory.glob(f"*{client_name}*{suffix}"):
                    files.append({
                        "protocol": proto,
                        "variant": variant,
                        "filename": path.name,
                        "path": str(path),
                    })
        return files

    def read_profile_file(self, path: str) -> str:
        file_path = Path(path).resolve()
        client_root = self.client_dir.resolve()
        if not str(file_path).startswith(str(client_root)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ к файлу запрещён")
        if not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
        return file_path.read_text(encoding="utf-8", errors="replace")

    _CONFIG_FILES = frozenset(
        {
            "include-hosts.txt",
            "exclude-hosts.txt",
            "include-ips.txt",
            "exclude-ips.txt",
            "allow-ips.txt",
            "drop-ips.txt",
            "forward-ips.txt",
            "include-adblock-hosts.txt",
            "exclude-adblock-hosts.txt",
            "remove-hosts.txt",
            "deny-ips.txt",
            "banned_clients",
        }
    )

    def read_config_file(self, filename: str) -> str:
        allowed = self._CONFIG_FILES
        if filename not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый конфигурационный файл")
        path = self.config_dir / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def write_config_file(self, filename: str, content: str) -> None:
        allowed = self._CONFIG_FILES
        if filename not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл недоступен для записи")
        path = self.config_dir / filename
        path.write_text(content, encoding="utf-8")

    def restart_service(self, service_name: str) -> str:
        allowed = {
            "openvpn-server@antizapret-udp",
            "openvpn-server@antizapret-tcp",
            "openvpn-server@vpn-udp",
            "openvpn-server@vpn-tcp",
            "wg-quick@antizapret",
            "wg-quick@vpn",
        }
        if service_name not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимое имя службы")
        try:
            result = subprocess.run(
                ["systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Таймаут перезапуска службы") from exc
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=output.strip() or "Ошибка перезапуска")
        return output.strip() or "ok"

    def apply_config_changes(self) -> str:
        doall = self.base_path / "doall.sh"
        if not doall.exists():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="doall.sh не найден")
        try:
            result = subprocess.run(
                [str(doall)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
                cwd=str(self.base_path),
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Таймаут обновления списков") from exc
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=output.strip())
        return output.strip()

    def get_server_ip(self) -> str | None:
        try:
            result = subprocess.run(
                ["bash", "-c", "ip route get 1.2.3.4 2>/dev/null | grep -oP 'src \\K\\S+'"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            ip = result.stdout.strip()
            return ip or None
        except (subprocess.TimeoutExpired, OSError):
            return None

    def get_antizapret_version(self) -> str | None:
        version_file = self.base_path / "VERSION"
        if version_file.is_file():
            version = version_file.read_text(encoding="utf-8", errors="replace").strip()
            if version:
                return version
        try:
            result = subprocess.run(
                ["git", "-C", str(self.base_path), "describe", "--tags", "--always"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                if version:
                    return version
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None

    def get_service_status(self) -> list[MonitoringService]:
        services = [
            "openvpn-server@antizapret-udp",
            "openvpn-server@antizapret-tcp",
            "openvpn-server@vpn-udp",
            "openvpn-server@vpn-tcp",
            "wg-quick@antizapret",
            "wg-quick@vpn",
        ]
        result_list: list[MonitoringService] = []
        for svc in services:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", svc],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                state = result.stdout.strip() or "unknown"
            except (subprocess.TimeoutExpired, OSError):
                state = "unknown"
            result_list.append(
                MonitoringService(
                    name=svc,
                    status=state,
                    active=state == "active",
                    description="Служба VPN" if "openvpn" in svc or "wg" in svc else None,
                )
            )
        return result_list

    def parse_openvpn_status(self) -> tuple[list[OpenVpnClient], str]:
        clients, data_source = openvpn_management_service.collect_clients(self.openvpn_logs)
        return clients, data_source

    def parse_openvpn_status_legacy(self) -> list[OpenVpnClient]:
        """Parse OpenVPN clients from *-status.log files (legacy fallback)."""
        clients: list[OpenVpnClient] = []
        if not self.openvpn_logs.exists():
            return clients
        for log_file in sorted(self.openvpn_logs.glob("*-status.log")):
            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            reader = csv.reader(io.StringIO(content))
            in_client_list = False
            for row in reader:
                if not row:
                    continue
                if row[0] == "HEADER" and len(row) > 1 and row[1] == "CLIENT_LIST":
                    in_client_list = True
                    continue
                if row[0] == "HEADER":
                    in_client_list = False
                    continue
                if row[0] == "END":
                    in_client_list = False
                    continue
                if in_client_list and row[0] == "CLIENT_LIST" and len(row) >= 9:
                    try:
                        clients.append(
                            OpenVpnClient(
                                common_name=row[1],
                                real_address=row[2],
                                virtual_address=row[3],
                                bytes_received=int(row[6] or 0),
                                bytes_sent=int(row[7] or 0),
                                connected_since=row[8],
                            )
                        )
                    except (ValueError, IndexError):
                        continue
        return clients

    def parse_wireguard_status(self) -> list[WireGuardPeer]:
        peers: list[WireGuardPeer] = []
        try:
            result = subprocess.run(["wg", "show", "all", "dump"], capture_output=True, text=True, timeout=10, check=False)
        except (subprocess.TimeoutExpired, OSError):
            return peers
        if result.returncode != 0:
            return peers

        wg_clients = self._load_wg_client_map()
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 9:
                continue
            interface, public_key, _psk, endpoint, allowed_ips, latest_handshake, rx, tx = parts[:8]
            client_name = wg_clients.get(public_key)
            handshake = None
            if latest_handshake and latest_handshake != "0":
                try:
                    handshake = datetime.utcfromtimestamp(int(latest_handshake)).isoformat()
                except ValueError:
                    handshake = latest_handshake
            peers.append(
                WireGuardPeer(
                    interface=interface,
                    public_key=public_key,
                    endpoint=endpoint or None,
                    allowed_ips=allowed_ips or None,
                    latest_handshake=handshake,
                    transfer_rx=int(rx or 0),
                    transfer_tx=int(tx or 0),
                    client_name=client_name,
                )
            )
        return peers

    def _load_wg_client_map(self) -> dict[str, str]:
        conf_paths = [Path("/etc/wireguard/antizapret.conf"), Path("/etc/wireguard/vpn.conf")]
        signature = tuple(
            (str(conf), conf.stat().st_mtime_ns if conf.exists() else None)
            for conf in conf_paths
        )
        cached = getattr(self, "_wg_client_map_cache", None)
        if cached and cached.get("signature") == signature:
            return dict(cached.get("mapping") or {})

        mapping: dict[str, str] = {}
        for conf in conf_paths:
            if not conf.exists():
                continue
            current_client: str | None = None
            for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# Client ="):
                    current_client = line.split("=", 1)[1].strip()
                elif line.strip().startswith("PublicKey =") and current_client:
                    pub = line.split("=", 1)[1].strip()
                    mapping[pub] = current_client
        self._wg_client_map_cache = {"signature": signature, "mapping": mapping}
        return mapping


antizapret_service = AntiZapretService()
