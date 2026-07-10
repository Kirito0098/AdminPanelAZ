"""WG/AWG runtime block/unblock (ported from AdminAntizapret wg_awg_runtime_enforcer)."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

WG_CONFIG_FILES = {
    "antizapret": Path("/etc/wireguard/antizapret.conf"),
    "vpn": Path("/etc/wireguard/vpn.conf"),
}

COMMAND_TIMEOUT_SECONDS = 10


def _normalize_client_name(client_name: str) -> str:
    return (client_name or "").strip().lower()


def _parse_peers(config_path: Path, interface_name: str, client_name: str) -> list[dict]:
    normalized = _normalize_client_name(client_name)
    if not config_path.exists():
        return []
    rows: list[dict] = []
    pending_client = ""
    current: dict | None = None

    def flush():
        nonlocal current
        if current and current.get("peer_public_key") and _normalize_client_name(current.get("client_name", "")) == normalized:
            rows.append({**current, "interface_name": interface_name})
        current = None

    for raw in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        m_client = re.match(r"^#\s*Client\s*=\s*(.+)$", line, re.I)
        if m_client:
            pending_client = m_client.group(1).strip()
            continue
        if re.match(r"^\[Peer\]$", line, re.I):
            flush()
            current = {"client_name": pending_client, "peer_public_key": "", "allowed_ips": "", "preshared_key": ""}
            pending_client = ""
            continue
        if current is None:
            continue
        m_pub = re.match(r"^PublicKey\s*=\s*(.+)$", line, re.I)
        if m_pub:
            current["peer_public_key"] = m_pub.group(1).strip()
            continue
        m_ips = re.match(r"^AllowedIPs\s*=\s*(.+)$", line, re.I)
        if m_ips:
            current["allowed_ips"] = m_ips.group(1).strip()
            continue
        m_psk = re.match(r"^PresharedKey\s*=\s*(.+)$", line, re.I)
        if m_psk:
            current["preshared_key"] = m_psk.group(1).strip()
    flush()
    return rows


def _peer_specs_for_client(client_name: str, *, config_files: dict[str, Path] | None = None) -> list[dict]:
    specs: list[dict] = []
    files = config_files or WG_CONFIG_FILES
    for iface, path in files.items():
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
    strip_result = _run(["wg-quick", "strip", interface_name], timeout=timeout)
    if strip_result.returncode != 0:
        return False, (strip_result.stderr or "").strip() or "wg-quick strip failed"

    stripped_config = strip_result.stdout or ""
    if not stripped_config.strip():
        return False, "empty stripped config"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as temp_file:
            temp_file.write(stripped_config)
            temp_path = temp_file.name
        sync_result = _run(["wg", "syncconf", interface_name, temp_path], timeout=timeout)
        if sync_result.returncode == 0:
            return True, ""
        return False, (sync_result.stderr or "").strip() or "wg syncconf failed"
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

    args = ["wg", "set", interface_name, "peer", peer_public_key]
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
        return False, (result.stderr or "").strip() or "wg set failed"
    finally:
        if psk_path:
            try:
                os.unlink(psk_path)
            except OSError:
                pass


def block_client_runtime(client_name: str) -> dict:
    peers = _collect_client_peers(client_name)
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
        result = _run(["wg", "set", interface_name, "peer", peer_public_key, "remove"])
        if result.returncode == 0:
            removed.append((interface_name, peer_public_key))
        else:
            errors.append(
                {
                    "interface": interface_name,
                    "peer_public_key": peer_public_key,
                    "stderr": (result.stderr or "").strip() or "wg set failed",
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


def sync_all_wireguard_interfaces(*, timeout: int = COMMAND_TIMEOUT_SECONDS) -> dict:
    """Apply on-disk WireGuard server configs to running interfaces via wg syncconf."""
    synced: list[str] = []
    errors: list[dict] = []
    for interface_name in sorted(WG_CONFIG_FILES):
        ok, stderr = _sync_interface_from_stripped_config(interface_name, timeout=timeout)
        if ok:
            synced.append(interface_name)
        else:
            errors.append({"interface": interface_name, "stderr": stderr})
    return {
        "success": not errors,
        "synced": synced,
        "error_count": len(errors),
        "errors": errors,
    }


def unblock_client_runtime(client_name: str) -> dict:
    config_files = WG_CONFIG_FILES
    specs = _peer_specs_for_client(client_name, config_files=config_files)
    restored: list[str] = []
    errors: list[dict] = []

    if specs:
        for spec in specs:
            ok, stderr = _restore_peer_spec(spec)
            if ok:
                restored.append(spec["interface_name"])
            else:
                errors.append({"interface": spec.get("interface_name"), "stderr": stderr})
        synced_count = len(restored)
        return {
            "success": synced_count > 0,
            "synced_count": synced_count,
            "restored": synced_count,
            "error_count": len(errors),
            "errors": errors,
        }

    peers = _collect_client_peers(client_name, config_files=config_files)
    interfaces = sorted({iface for iface, _ in peers if iface})
    if not interfaces:
        interfaces = sorted(config_files.keys())

    synced: list[str] = []
    for interface_name in interfaces:
        config_path = config_files.get(interface_name)
        if config_path is None or not str(config_path).strip():
            continue
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
