"""AWG runtime block/unblock helpers mirroring wg_runtime semantics."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

AWG2_CONFIG_DIR = Path("/etc/amnezia/amneziawg")
DEFAULT_AZ_IFACE = "antizapret-awg"
DEFAULT_VPN_IFACE = "vpn-awg"
COMMAND_TIMEOUT_SECONDS = 10


def _normalize_client_name(client_name: str) -> str:
    return (client_name or "").strip().lower()


def _read_kv_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _build_config_files(config_dir: Path | str = AWG2_CONFIG_DIR) -> dict[str, Path]:
    root = Path(config_dir)
    env = _read_kv_file(root / "services.env")
    interfaces = [
        (env.get("AZ_IFACE") or DEFAULT_AZ_IFACE).strip(),
        (env.get("VPN_IFACE") or DEFAULT_VPN_IFACE).strip(),
    ]
    return {iface: root / f"{iface}.conf" for iface in interfaces if iface}


def _resolve_config_files(config_files: dict[str, Path] | None = None) -> dict[str, Path]:
    return config_files or _build_config_files()


def _comment_client_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("#") or len(stripped) <= 1:
        return None
    comment = stripped[1:].strip()
    if not comment:
        return None
    lowered = comment.lower()
    if lowered.startswith("privatekey") or lowered.startswith("presharedkey"):
        return None
    match = re.match(r"^client\s*=\s*(.+)$", comment, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return comment


def _parse_peers(config_path: Path, interface_name: str, client_name: str) -> list[dict]:
    normalized = _normalize_client_name(client_name)
    if not config_path.exists():
        return []

    rows: list[dict] = []
    pending_client = ""
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current and current.get("peer_public_key") and _normalize_client_name(current.get("client_name", "")) == normalized:
            rows.append({**current, "interface_name": interface_name})
        current = None

    for raw in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue

        parsed_client_name = _comment_client_name(line)
        if parsed_client_name is not None:
            if current is not None and not current.get("peer_public_key"):
                current["client_name"] = parsed_client_name
            else:
                pending_client = parsed_client_name
            continue

        if re.match(r"^\[Peer\]$", line, re.IGNORECASE):
            flush()
            current = {
                "client_name": pending_client,
                "peer_public_key": "",
                "allowed_ips": "",
                "preshared_key": "",
            }
            pending_client = ""
            continue

        if current is None:
            continue

        match = re.match(r"^PublicKey\s*=\s*(.+)$", line, re.IGNORECASE)
        if match:
            current["peer_public_key"] = match.group(1).strip()
            continue

        match = re.match(r"^AllowedIPs\s*=\s*(.+)$", line, re.IGNORECASE)
        if match:
            current["allowed_ips"] = match.group(1).strip()
            continue

        match = re.match(r"^PresharedKey\s*=\s*(.+)$", line, re.IGNORECASE)
        if match:
            current["preshared_key"] = match.group(1).strip()

    flush()
    return rows


def _peer_specs_for_client(client_name: str, *, config_files: dict[str, Path] | None = None) -> list[dict]:
    specs: list[dict] = []
    for iface, path in _resolve_config_files(config_files).items():
        specs.extend(_parse_peers(path, iface, client_name))
    return specs


def _collect_client_peers(client_name: str, *, config_files: dict[str, Path] | None = None) -> list[tuple[str, str]]:
    return [
        (spec["interface_name"], spec["peer_public_key"])
        for spec in _peer_specs_for_client(client_name, config_files=config_files)
        if spec.get("interface_name") and spec.get("peer_public_key")
    ]


def _run(args: list[str], timeout: int = COMMAND_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _sync_interface_from_stripped_config(interface_name: str, *, timeout: int = COMMAND_TIMEOUT_SECONDS) -> tuple[bool, str]:
    strip_result = _run(["awg-quick", "strip", interface_name], timeout=timeout)
    if strip_result.returncode != 0:
        return False, (strip_result.stderr or strip_result.stdout or "awg-quick strip failed").strip()

    stripped_config = strip_result.stdout or ""
    if not stripped_config.strip():
        return False, "empty stripped config"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as temp_file:
            temp_file.write(stripped_config)
            temp_path = temp_file.name
        sync_result = _run(["awg", "syncconf", interface_name, temp_path], timeout=timeout)
        if sync_result.returncode == 0:
            return True, ""
        return False, (sync_result.stderr or sync_result.stdout or "awg syncconf failed").strip()
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _restore_peer_spec(spec: dict, *, timeout: int = COMMAND_TIMEOUT_SECONDS) -> tuple[bool, str]:
    interface_name = (spec.get("interface_name") or "").strip()
    peer_public_key = (spec.get("peer_public_key") or "").strip()
    if not interface_name or not peer_public_key:
        return False, "missing interface or public key"

    args = ["awg", "set", interface_name, "peer", peer_public_key]
    allowed_ips = (spec.get("allowed_ips") or "").strip()
    if allowed_ips:
        args.extend(["allowed-ips", allowed_ips])

    preshared_key = (spec.get("preshared_key") or "").strip()
    psk_path = None
    try:
        if preshared_key:
            with tempfile.NamedTemporaryFile(mode="wb", suffix=".psk", delete=False) as psk_file:
                psk_file.write(preshared_key.encode("ascii"))
                psk_path = psk_file.name
            args.extend(["preshared-key", psk_path])

        result = _run(args, timeout=timeout)
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or result.stdout or "awg set failed").strip()
    finally:
        if psk_path:
            try:
                os.unlink(psk_path)
            except OSError:
                pass


def block_client_runtime(client_name: str, *, config_files: dict[str, Path] | None = None) -> dict:
    peers = _collect_client_peers(client_name, config_files=config_files)
    if not peers:
        return {
            "success": False,
            "removed_count": 0,
            "blocked": 0,
            "error_count": 1,
            "errors": [{"interface": None, "stderr": "Пиры клиента не найдены"}],
        }

    removed: list[tuple[str, str]] = []
    errors: list[dict] = []
    for interface_name, peer_public_key in peers:
        result = _run(["awg", "set", interface_name, "peer", peer_public_key, "remove"])
        if result.returncode == 0:
            removed.append((interface_name, peer_public_key))
        else:
            errors.append(
                {
                    "interface": interface_name,
                    "peer_public_key": peer_public_key,
                    "stderr": (result.stderr or result.stdout or "awg set failed").strip(),
                }
            )

    removed_count = len(removed)
    return {
        "success": removed_count > 0,
        "removed_count": removed_count,
        "blocked": removed_count,
        "error_count": len(errors),
        "errors": errors,
    }


def unblock_client_runtime(client_name: str, *, config_files: dict[str, Path] | None = None) -> dict:
    files = _resolve_config_files(config_files)
    specs = _peer_specs_for_client(client_name, config_files=files)
    restored: list[str] = []
    errors: list[dict] = []

    if specs:
        for spec in specs:
            ok, stderr = _restore_peer_spec(spec)
            if ok:
                restored.append(spec["interface_name"])
            else:
                errors.append({"interface": spec.get("interface_name"), "stderr": stderr})
        restored_count = len(restored)
        return {
            "success": restored_count > 0,
            "synced_count": restored_count,
            "restored": restored_count,
            "error_count": len(errors),
            "errors": errors,
        }

    interfaces = sorted(files.keys())
    synced: list[str] = []
    for interface_name in interfaces:
        ok, stderr = _sync_interface_from_stripped_config(interface_name)
        if ok:
            synced.append(interface_name)
        else:
            errors.append({"interface": interface_name, "stderr": stderr})

    synced_count = len(synced)
    return {
        "success": synced_count > 0,
        "synced_count": synced_count,
        "restored": synced_count,
        "error_count": len(errors),
        "errors": errors,
    }
