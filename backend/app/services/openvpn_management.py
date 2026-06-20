"""OpenVPN management Unix socket reader (ported from AdminAntizapret)."""

from __future__ import annotations

import csv
import io
import os
import re
import socket
import time
from pathlib import Path

from app.config import get_settings
from app.schemas import OpenVpnClient

OPENVPN_PROFILES = ("antizapret-tcp", "antizapret-udp", "vpn-tcp", "vpn-udp")

_CLIENT_PATTERN = re.compile(
    r"CLIENT_LIST,([^,\n]+),([^,\n]+),([^,\n]*),([^,\n]*),(\d+),(\d+),([^,\n]+),(\d+),([^,\n]*),([^,\n]*),([^,\n]*),([^,\n\r ]+)"
)
_CLIENT_PATTERN_TAB = re.compile(
    r"^CLIENT_LIST\s+(\S+)\s+(\S+)\s+(\S+)\s+(?:(\S+)\s+)?(\d+)\s+(\d+)\s+"
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\S+)",
    re.MULTILINE,
)


class OpenVpnManagementService:
    def __init__(
        self,
        *,
        openvpn_socket_dir: Path | str | None = None,
        openvpn_socket_timeout: float | None = None,
        openvpn_socket_idle_timeout: float | None = None,
        openvpn_log_tail_lines: int | None = None,
        openvpn_event_max_response_bytes: int | None = None,
    ):
        settings = get_settings()
        self.openvpn_socket_dir = Path(openvpn_socket_dir or settings.openvpn_socket_dir)
        self.openvpn_socket_timeout = float(
            openvpn_socket_timeout if openvpn_socket_timeout is not None else settings.openvpn_socket_timeout
        )
        self.openvpn_socket_idle_timeout = float(
            openvpn_socket_idle_timeout
            if openvpn_socket_idle_timeout is not None
            else settings.openvpn_socket_idle_timeout
        )
        self.openvpn_log_tail_lines = int(
            openvpn_log_tail_lines if openvpn_log_tail_lines is not None else settings.openvpn_log_tail_lines
        )
        self.openvpn_event_max_response_bytes = int(
            openvpn_event_max_response_bytes
            if openvpn_event_max_response_bytes is not None
            else settings.openvpn_event_max_response_bytes
        )

    def openvpn_socket_path(self, profile_key: str) -> Path:
        return self.openvpn_socket_dir / f"{profile_key}.sock"

    def query_openvpn_management_socket(
        self,
        socket_path: Path | str,
        command: str,
        max_response_bytes: int = 0,
    ) -> str:
        socket_path = Path(socket_path)
        if not socket_path.exists():
            return ""

        cmd = (command or "").strip()
        if not cmd:
            return ""

        max_response_bytes = int(max_response_bytes or 0)
        received_bytes = 0

        def _append_chunk(raw_bytes: bytes, target: list[str]) -> bool:
            nonlocal received_bytes
            if not raw_bytes:
                return False

            if max_response_bytes > 0:
                remaining = max_response_bytes - received_bytes
                if remaining <= 0:
                    return True
                if len(raw_bytes) > remaining:
                    raw_bytes = raw_bytes[:remaining]
                    target.append(raw_bytes.decode("utf-8", errors="ignore"))
                    received_bytes += len(raw_bytes)
                    return True

            target.append(raw_bytes.decode("utf-8", errors="ignore"))
            received_bytes += len(raw_bytes)
            return False

        chunks: list[str] = []
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock_conn:
                sock_conn.settimeout(self.openvpn_socket_timeout)
                sock_conn.connect(str(socket_path))

                try:
                    banner = sock_conn.recv(65536)
                    if banner:
                        if _append_chunk(banner, chunks):
                            return "".join(chunks)
                except socket.timeout:
                    pass

                sock_conn.sendall((cmd + "\n").encode("utf-8", errors="ignore"))

                idle_timeout = self.openvpn_socket_idle_timeout
                is_status_cmd = cmd.lower().startswith("status")
                read_deadline = time.monotonic() + (1.4 if is_status_cmd else 0.9)
                got_payload = False
                timeout_streak = 0
                end_probe = ""

                while time.monotonic() < read_deadline:
                    try:
                        sock_conn.settimeout(idle_timeout)
                        data = sock_conn.recv(65536)
                    except socket.timeout:
                        timeout_streak += 1
                        if got_payload and timeout_streak >= 2:
                            break
                        continue
                    if not data:
                        break
                    hit_limit = _append_chunk(data, chunks)
                    text_chunk = chunks[-1] if chunks else ""
                    got_payload = True
                    timeout_streak = 0
                    if is_status_cmd:
                        end_probe = (end_probe + text_chunk)[-256:]
                        if re.search(r"(^|\n)END(\n|$)", end_probe):
                            break
                    if hit_limit:
                        break

                try:
                    sock_conn.sendall(b"quit\n")
                except OSError:
                    pass

                try:
                    sock_conn.settimeout(0.05)
                    while True:
                        tail = sock_conn.recv(65536)
                        if not tail:
                            break
                        if _append_chunk(tail, chunks):
                            break
                except OSError:
                    pass
        except OSError:
            return ""

        return "".join(chunks)

    def extract_status_payload_from_management(self, raw: str) -> str:
        lines: list[str] = []
        for raw_line in (raw or "").splitlines():
            line = raw_line.strip("\r")
            if not line:
                continue
            if (
                line.startswith("TITLE,")
                or line.startswith("TIME,")
                or line.startswith("HEADER,")
                or line.startswith("TITLE\t")
                or line.startswith("TIME\t")
                or line.startswith("HEADER\t")
                or line.startswith("TITLE ")
                or line.startswith("TIME ")
                or line.startswith("HEADER ")
            ):
                lines.append(line)
                continue
            if (
                line.startswith("CLIENT_LIST,")
                or line.startswith("ROUTING_TABLE,")
                or line.startswith("GLOBAL_STATS,")
                or line.startswith("CLIENT_LIST\t")
                or line.startswith("ROUTING_TABLE\t")
                or line.startswith("GLOBAL_STATS\t")
                or line.startswith("CLIENT_LIST ")
                or line.startswith("ROUTING_TABLE ")
                or line.startswith("GLOBAL_STATS ")
            ):
                lines.append(line)
                continue
            if line == "END":
                lines.append(line)

        return "\n".join(lines)

    def extract_event_payload_from_management(self, raw: str) -> str:
        lines: list[str] = []
        for raw_line in (raw or "").splitlines():
            line = raw_line.strip("\r")
            if not line:
                continue

            if line.startswith(">LOG:"):
                parts = line.split(",", 2)
                msg = parts[2] if len(parts) >= 3 else ""
                msg = msg.strip()
                if msg:
                    lines.append(msg)
                continue

            if any(token in line for token in ("Peer Connection Initiated", "VERIFY OK", "peer info:")):
                lines.append(line)

        return "\n".join(lines)

    def read_status_source(self, profile_key: str) -> dict:
        socket_path = self.openvpn_socket_path(profile_key)
        raw_mgmt = self.query_openvpn_management_socket(socket_path, "status 3")
        payload = self.extract_status_payload_from_management(raw_mgmt)
        if payload:
            return {
                "raw": payload,
                "source_name": socket_path.name,
                "exists": True,
                "updated_at_ts": int(time.time()),
                "source_type": "socket",
            }

        return {
            "raw": "",
            "source_name": socket_path.name,
            "exists": False,
            "updated_at_ts": 0,
            "source_type": "socket",
        }

    def read_event_source(self, profile_key: str) -> dict:
        socket_path = self.openvpn_socket_path(profile_key)
        if not socket_path.exists():
            return {
                "raw": "",
                "source_name": socket_path.name,
                "exists": False,
                "updated_at_ts": 0,
                "source_type": "socket",
            }

        log_cmd = "log all" if self.openvpn_log_tail_lines == 0 else f"log {self.openvpn_log_tail_lines}"
        raw_mgmt = self.query_openvpn_management_socket(
            socket_path,
            log_cmd,
            max_response_bytes=self.openvpn_event_max_response_bytes,
        )
        payload = self.extract_event_payload_from_management(raw_mgmt)
        lines = [line for line in payload.splitlines() if line.strip()]
        return {
            "raw": payload,
            "source_name": socket_path.name,
            "exists": True,
            "updated_at_ts": int(time.time()) if lines else 0,
            "source_type": "socket",
        }

    def parse_clients_from_status_raw(
        self,
        raw: str,
        profile_key: str,
        *,
        data_source: str = "management_socket",
    ) -> list[OpenVpnClient]:
        clients: list[OpenVpnClient] = []

        for match in _CLIENT_PATTERN.finditer(raw):
            clients.append(
                OpenVpnClient(
                    common_name=match.group(1).strip(),
                    real_address=match.group(2).strip(),
                    virtual_address=match.group(3).strip(),
                    bytes_received=int(match.group(5) or 0),
                    bytes_sent=int(match.group(6) or 0),
                    connected_since=match.group(7).strip(),
                    connected_since_ts=int(match.group(8) or 0),
                    profile=profile_key,
                    data_source=data_source,
                )
            )

        if clients:
            return clients

        for match in _CLIENT_PATTERN_TAB.finditer(raw):
            clients.append(
                OpenVpnClient(
                    common_name=match.group(1).strip(),
                    real_address=match.group(2).strip(),
                    virtual_address=match.group(3).strip(),
                    bytes_received=int(match.group(5) or 0),
                    bytes_sent=int(match.group(6) or 0),
                    connected_since=match.group(7).strip(),
                    connected_since_ts=int(match.group(8) or 0),
                    profile=profile_key,
                    data_source=data_source,
                )
            )

        return clients

    def parse_clients_from_status_log_file(self, log_file: Path, profile_key: str) -> list[OpenVpnClient]:
        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        clients: list[OpenVpnClient] = []
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
                            connected_since_ts=int(row[8]) if str(row[8]).isdigit() else 0,
                            profile=profile_key,
                            data_source="status_log",
                        )
                    )
                except (ValueError, IndexError):
                    continue
        return clients

    def collect_clients(self, status_log_dir: Path | str | None = None) -> tuple[list[OpenVpnClient], str]:
        """Collect OpenVPN clients via management socket with status-log fallback."""
        log_dir = Path(status_log_dir) if status_log_dir else None
        clients: list[OpenVpnClient] = []
        used_socket = False
        used_logs = False

        for profile_key in OPENVPN_PROFILES:
            source = self.read_status_source(profile_key)
            if source.get("exists") and source.get("raw"):
                used_socket = True
                clients.extend(
                    self.parse_clients_from_status_raw(
                        source["raw"],
                        profile_key,
                        data_source="management_socket",
                    )
                )
                continue

            if log_dir:
                log_file = log_dir / f"{profile_key}-status.log"
                parsed = self.parse_clients_from_status_log_file(log_file, profile_key)
                if parsed:
                    used_logs = True
                    clients.extend(parsed)

        if used_socket:
            return clients, "management_socket"
        if used_logs:
            return clients, "status_log"
        return clients, "none"

    def active_openvpn_profiles(self) -> tuple[str, ...]:
        return tuple(
            profile_key
            for profile_key in OPENVPN_PROFILES
            if self.openvpn_socket_path(profile_key).exists()
        )

    def collect_events(self) -> list[dict]:
        rows: list[dict] = []
        for profile_key in self.active_openvpn_profiles():
            source = self.read_event_source(profile_key)
            raw = source.get("raw") or ""
            lines = [line for line in raw.splitlines() if line.strip()]
            rows.append(
                {
                    "profile": profile_key,
                    "source_name": source.get("source_name", ""),
                    "exists": True,
                    "updated_at_ts": int(source.get("updated_at_ts") or 0),
                    "line_count": len(lines),
                    "recent_lines": lines[-50:],
                }
            )
        return rows

    def kill_client(self, profile_key: str, client_name: str) -> dict:
        """Force-disconnect an OpenVPN client via management socket kill command."""
        socket_path = self.openvpn_socket_path(profile_key)
        if not socket_path.exists():
            return {"success": False, "message": f"Сокет {profile_key} недоступен"}
        cmd = f"kill {client_name}"
        raw = self.query_openvpn_management_socket(socket_path, cmd)
        success = "SUCCESS" in raw.upper() or "killed" in raw.lower() or bool(raw.strip())
        return {
            "success": success,
            "profile": profile_key,
            "client_name": client_name,
            "message": "Клиент отключён" if success else (raw.strip() or "Не удалось отключить клиента"),
            "raw": raw[:500],
        }

    def disconnect_client(self, client_name: str) -> dict:
        """Try kill on all profiles where client is connected."""
        for profile_key in OPENVPN_PROFILES:
            source = self.read_status_source(profile_key)
            if not source.get("raw"):
                continue
            clients = self.parse_clients_from_status_raw(source["raw"], profile_key)
            if any(c.common_name == client_name for c in clients):
                result = self.kill_client(profile_key, client_name)
                if result.get("success"):
                    return result
        return {"success": False, "message": f"Клиент {client_name} не найден среди подключённых"}

    def get_socket_status(self) -> list[dict]:
        rows: list[dict] = []
        for profile_key in OPENVPN_PROFILES:
            socket_path = self.openvpn_socket_path(profile_key)
            exists = socket_path.exists()
            responsive = False
            if exists:
                probe = self.query_openvpn_management_socket(socket_path, "status 3")
                responsive = bool(self.extract_status_payload_from_management(probe))
            rows.append(
                {
                    "profile": profile_key,
                    "socket_path": str(socket_path),
                    "socket_exists": exists,
                    "responsive": responsive,
                }
            )
        return rows


openvpn_management_service = OpenVpnManagementService()
