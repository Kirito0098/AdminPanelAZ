"""Simplified WG/AWG runtime block/unblock (ported from AdminAntizapret)."""

import re
import subprocess
from pathlib import Path


WG_CONFIG_FILES = {
    "antizapret": Path("/etc/wireguard/antizapret.conf"),
    "vpn": Path("/etc/wireguard/vpn.conf"),
}


def _parse_peers(config_path: Path, interface_name: str, client_name: str) -> list[dict]:
    normalized = client_name.strip().lower()
    if not config_path.exists():
        return []
    rows: list[dict] = []
    pending_client = ""
    current: dict | None = None

    def flush():
        nonlocal current
        if current and current.get("peer_public_key") and current.get("client_name", "").strip().lower() == normalized:
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


def _run(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def block_client_runtime(client_name: str) -> dict:
    specs = []
    for iface, path in WG_CONFIG_FILES.items():
        specs.extend(_parse_peers(path, iface, client_name))
    if not specs:
        return {"success": False, "error": "Пиры клиента не найдены", "blocked": 0}

    blocked = 0
    errors: list[str] = []
    for spec in specs:
        result = _run(["wg", "set", spec["interface_name"], "peer", spec["peer_public_key"], "remove"])
        if result.returncode == 0:
            blocked += 1
        else:
            errors.append(result.stderr.strip() or "wg set failed")
    return {"success": blocked > 0, "blocked": blocked, "errors": errors}


def unblock_client_runtime(client_name: str) -> dict:
    specs = []
    for iface, path in WG_CONFIG_FILES.items():
        specs.extend(_parse_peers(path, iface, client_name))
    if not specs:
        return {"success": False, "error": "Пиры клиента не найдены", "restored": 0}

    restored = 0
    errors: list[str] = []
    for spec in specs:
        args = ["wg", "set", spec["interface_name"], "peer", spec["peer_public_key"]]
        if spec.get("allowed_ips"):
            args.extend(["allowed-ips", spec["allowed_ips"]])
        if spec.get("preshared_key"):
            args.extend(["preshared-key", spec["preshared_key"]])
        result = _run(args)
        if result.returncode == 0:
            restored += 1
        else:
            errors.append(result.stderr.strip() or "wg set failed")
    return {"success": restored > 0, "restored": restored, "errors": errors}
