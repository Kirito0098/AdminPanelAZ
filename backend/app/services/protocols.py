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
    "amneziawg2": "amneziawg2",
    "awg2": "amneziawg2",
    "awg 2.0": "amneziawg2",
}

CANONICAL_PROTOCOLS = frozenset({"openvpn", "wireguard", "amneziawg", "amneziawg2"})

PROTOCOL_LABELS: dict[str, str] = {
    "openvpn": "OpenVPN",
    "wireguard": "WireGuard",
    "amneziawg": "AmneziaWG",
    "amneziawg2": "AmneziaWG 2.0",
}


def normalize_protocol(protocol: str | None) -> str:
    key = (protocol or "").strip().lower()
    return PROTOCOL_ALIASES.get(key, key)


def protocol_label(protocol: str | None) -> str:
    return PROTOCOL_LABELS.get(normalize_protocol(protocol), "неизвестно")
