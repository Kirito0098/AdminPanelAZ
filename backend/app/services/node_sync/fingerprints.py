"""SHA256 fingerprints of AntiZapret HA-critical paths."""

from __future__ import annotations

import hashlib
from pathlib import Path

# HA-local config files under {antizapret}/config/ — excluded from parity verify and
# from blind full-directory push to replicas (node-specific state must not fail Verify
# or overwrite peer nodes).
#
# Current entries:
# - warper-include-ips.txt — WARPER slave routing on a single node (AZ-WARP); other
#   replicas may omit this file or keep a different copy.
#
# Add new filenames here when a path is intentionally per-node in HA auto-sync.
CONFIG_FINGERPRINT_EXCLUDE: frozenset[str] = frozenset({"warper-include-ips.txt"})


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _sha256_directory_glob(
    directory: Path,
    pattern: str,
    *,
    exclude_names: frozenset[str] | None = None,
) -> str | None:
    if not directory.is_dir():
        return None
    files = sorted(directory.glob(pattern))
    if not files:
        return None
    hasher = hashlib.sha256()
    included = False
    for file_path in files:
        if not file_path.is_file():
            continue
        if exclude_names and file_path.name in exclude_names:
            continue
        included = True
        hasher.update(file_path.name.encode())
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                hasher.update(chunk)
    if not included:
        return None
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

    config_hash = _sha256_directory_glob(
        base / "config",
        "*",
        exclude_names=CONFIG_FINGERPRINT_EXCLUDE,
    )
    if config_hash:
        fingerprints["antizapret/config"] = config_hash

    return fingerprints
