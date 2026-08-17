from __future__ import annotations

import logging
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.models import Node, VpnType
from app.services.openvpn_remote_hosts import apply_openvpn_remote_hosts, parse_hosts_json
from app.services.vpn_profile_visibility import protocol_key_from_file
from app.services.wireguard_endpoint import apply_wireguard_endpoint_host

logger = logging.getLogger(__name__)


def load_node_remote_hosts(db: Session, node_id: int | None) -> list[str]:
    if not node_id:
        return []
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        return []
    return parse_hosts_json(node.openvpn_remote_hosts)


def patch_openvpn_profiles_on_node(adapter, hosts: list[str]) -> dict:
    """Rewrite remote lines in on-disk .ovpn files after client.sh 7.

    Empty ``hosts`` is a no-op. Failures on individual files are collected in
    ``warnings``; they never undo a completed recreate.
    """
    if not hosts:
        return {"patched": 0, "warnings": []}
    patched = 0
    warnings: list[str] = []
    try:
        names = adapter.list_openvpn_clients()
    except Exception as exc:  # noqa: BLE001
        return {"patched": 0, "warnings": [str(exc)]}
    seen_paths: set[str] = set()
    for name in names:
        try:
            files = adapter.get_profile_files(name, VpnType.openvpn)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{name}: {exc}")
            continue
        for item in files:
            path = item.get("path") or ""
            if not path or not path.lower().endswith(".ovpn") or path in seen_paths:
                continue
            seen_paths.add(path)
            try:
                raw = adapter.read_profile_file(path)
                new = apply_openvpn_remote_hosts(raw, hosts)
                if new != raw:
                    adapter.write_profile_file(path, new)
                    patched += 1
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{path}: {exc}")
    if warnings:
        logger.warning(
            "OpenVPN remote-hosts disk patch: %s file(s) ok, warnings=%s",
            patched,
            warnings,
        )
    return {"patched": patched, "warnings": warnings}


def wireguard_host_from_adapter(adapter) -> str:
    """Live WIREGUARD_HOST from AntiZapret setup on the node (client.sh source)."""
    try:
        raw = adapter.get_antizapret_settings()
    except Exception:  # noqa: BLE001 — delivery must still return the file
        return ""
    if not isinstance(raw, dict):
        return ""
    host = raw.get("wireguard_host")
    if not isinstance(host, str):
        return ""
    return host.strip()


def read_profile_file_for_delivery(adapter, path: str, hosts: list[str]) -> str:
    raw = adapter.read_profile_file(path)
    name = PurePosixPath(path.replace("\\", "/")).name
    if name.lower().endswith(".ovpn"):
        return apply_openvpn_remote_hosts(raw, hosts)
    proto = protocol_key_from_file(protocol="", path=path)
    if proto in ("wireguard", "amneziawg"):
        # GubernievS: Endpoint host is WIREGUARD_HOST, never the OpenVPN remote list.
        # Proxy for AWG is opt-in (remotes save with apply_to_wireguard writes WIREGUARD_HOST).
        return apply_wireguard_endpoint_host(raw, wireguard_host_from_adapter(adapter))
    return raw
