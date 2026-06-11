"""Helpers for matching VPN profile files on disk to panel clients."""

from __future__ import annotations

from pathlib import Path

from app.models import VpnType

PROFILE_PREFIXES = (
    "antizapret-udp",
    "antizapret-tcp",
    "antizapret",
    "vpn-udp",
    "vpn-tcp",
    "vpn",
)


def profile_files_batch_key(client_name: str, vpn_type: VpnType | str) -> str:
    vt = vpn_type.value if isinstance(vpn_type, VpnType) else str(vpn_type)
    return f"{client_name}\x1e{vt}"


def extract_client_from_profile_filename(filename: str) -> str | None:
    for prefix in PROFILE_PREFIXES:
        token = f"{prefix}-"
        if not filename.startswith(token):
            continue
        rest = filename[len(token) :]
        end = rest.find("-(")
        if end != -1:
            return rest[:end]
    return None


def profile_filename_matches_client(filename: str, client_name: str, *, suffix: str = "") -> bool:
    if suffix and not filename.endswith(suffix):
        return False
    extracted = extract_client_from_profile_filename(filename)
    if extracted is not None:
        return extracted == client_name
    return client_name in filename


def iter_client_profile_paths(directory: Path, client_name: str, suffix: str) -> list[Path]:
    if not directory.is_dir():
        return []
    matches: list[Path] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        if profile_filename_matches_client(path.name, client_name, suffix=suffix):
            matches.append(path)
    return matches
