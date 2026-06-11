"""Human-friendly download filenames for VPN profile files."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

CLIENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
AZ_PROFILE_DIR = re.compile(r"/(?:openvpn|wireguard|amneziawg)/antizapret(?:[-/]|$)")


def sanitize_client_name(client_name: str) -> str:
    name = (client_name or "").strip()
    if CLIENT_NAME_RE.match(name):
        return name
    return "client"


def _parse_profile_location(path: str) -> tuple[str, str]:
    parts = PurePosixPath(path).parts
    if "client" not in parts:
        return "", ""
    idx = parts.index("client")
    if idx + 2 >= len(parts):
        return "", ""
    return parts[idx + 1], parts[idx + 2]


def _is_az_profile(*, variant: str, path: str) -> bool:
    if "antizapret" in variant:
        return True
    return bool(AZ_PROFILE_DIR.search(path.replace("\\", "/")))


def _openvpn_suffix(variant: str, path: str) -> str:
    normalized = f"{variant} {PurePosixPath(path).name}".lower()
    if "-udp" in normalized:
        return "-udp"
    if "-tcp" in normalized:
        return "-tcp"
    return ""


def build_profile_download_filename(
    client_name: str,
    *,
    protocol: str = "",
    variant: str = "",
    path: str = "",
) -> str:
    safe_name = sanitize_client_name(client_name)
    proto = (protocol or _parse_profile_location(path)[0]).lower()
    variant = variant or _parse_profile_location(path)[1]
    profile_prefix = "AZ" if _is_az_profile(variant=variant, path=path) else "VPN"

    if proto == "openvpn":
        suffix = _openvpn_suffix(variant, path)
        return f"{profile_prefix}-{safe_name}{suffix}.ovpn"
    if proto == "wireguard":
        return f"WG-{profile_prefix}-{safe_name}.conf"
    if proto == "amneziawg":
        return f"AWG-{profile_prefix}-{safe_name}.conf"

    raw = PurePosixPath(path).name if path else f"{profile_prefix}-{safe_name}.txt"
    return raw or f"{profile_prefix}-{safe_name}.txt"


def enrich_profile_files(client_name: str, files: list[dict[str, str]]) -> list[dict[str, str]]:
    enriched: list[dict[str, str]] = []
    for item in files:
        row = dict(item)
        row["download_filename"] = build_profile_download_filename(
            client_name,
            protocol=item.get("protocol", ""),
            variant=item.get("variant", ""),
            path=item.get("path", ""),
        )
        enriched.append(row)
    return enriched
