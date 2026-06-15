"""SHA256 fingerprints of AntiZapret HA-critical paths."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _sha256_directory_glob(directory: Path, pattern: str) -> str | None:
    if not directory.is_dir():
        return None
    files = sorted(directory.glob(pattern))
    if not files:
        return None
    hasher = hashlib.sha256()
    for file_path in files:
        if not file_path.is_file():
            continue
        hasher.update(file_path.name.encode())
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                hasher.update(chunk)
    return hasher.hexdigest()


def collect_antizapret_fingerprints(install_dir: str | Path = "/root/antizapret") -> dict[str, str]:
    """Return stable path keys → sha256 hex for parity verify."""
    base = Path(install_dir or "/root/antizapret").resolve()
    entries: list[tuple[str, Path]] = [
        ("easyrsa3/pki/ca.crt", Path("/etc/openvpn/easyrsa3/pki/ca.crt")),
        ("easyrsa3/pki/index.txt", Path("/etc/openvpn/easyrsa3/pki/index.txt")),
        ("easyrsa3/pki/serial", Path("/etc/openvpn/easyrsa3/pki/serial")),
    ]
    fingerprints: dict[str, str] = {}
    for key, path in entries:
        digest = _sha256_file(path)
        if digest:
            fingerprints[key] = digest

    wg_hash = _sha256_directory_glob(Path("/etc/wireguard"), "*.conf")
    if wg_hash:
        fingerprints["wireguard/conf_files"] = wg_hash

    config_hash = _sha256_directory_glob(base / "config", "*")
    if config_hash:
        fingerprints["antizapret/config"] = config_hash

    return fingerprints
