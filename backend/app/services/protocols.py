"""Canonical VPN protocol names, aliases and user-facing labels."""

from __future__ import annotations

PROTOCOL_ALIASES: dict[str, str] = {
    "openvpn": "openvpn",
    "ovpn": "openvpn",
    "wireguard": "wireguard",
    "wg": "wireguard",
    "amneziawg": "amneziawg",
    "awg": "amneziawg",
    "amnezia": "amneziawg",
    "awg 1.5": "amneziawg",
    "wg/awg 1.5": "amneziawg",
    "amneziawg2": "amneziawg2",
    "awg2": "amneziawg2",
    "awg 2.0": "amneziawg2",
    "amneziawg 2.0": "amneziawg2",
    "wg 2.0": "amneziawg2",
}

CANONICAL_PROTOCOLS = frozenset({"openvpn", "wireguard", "amneziawg", "amneziawg2"})

# Full names — only for explanatory prose.
PROTOCOL_LABELS: dict[str, str] = {
    "openvpn": "OpenVPN",
    "wireguard": "WireGuard",
    "amneziawg": "AmneziaWG",
    "amneziawg2": "AmneziaWG 2.0",
}

# Badges/chips: WG/AWG 1.5 is shared by wireguard and stock amneziawg.
PROTOCOL_BADGES: dict[str, str] = {
    "openvpn": "OpenVPN",
    "wireguard": "WG/AWG 1.5",
    "amneziawg": "WG/AWG 1.5",
    "amneziawg2": "AWG 2.0",
}

# Module names (settings pickers, protocol cards).
PROTOCOL_MODULE_LABELS: dict[str, str] = {
    "openvpn": "OpenVPN",
    "wireguard": "WireGuard",
    "amneziawg": "AmneziaWG 1.5",
    "amneziawg2": "AWG 2.0",
}


def normalize_protocol(protocol: str | None) -> str:
    key = (protocol or "").strip().lower()
    return PROTOCOL_ALIASES.get(key, key)


def protocol_label(protocol: str | None) -> str:
    """Full protocol name for prose; unknown values fall back to the raw key."""
    key = normalize_protocol(protocol)
    return PROTOCOL_LABELS.get(key, key)


def protocol_badge(protocol: str | None) -> str:
    key = normalize_protocol(protocol)
    return PROTOCOL_BADGES.get(key, key)


def protocol_module_label(protocol: str | None) -> str:
    key = normalize_protocol(protocol)
    return PROTOCOL_MODULE_LABELS.get(key, key)
