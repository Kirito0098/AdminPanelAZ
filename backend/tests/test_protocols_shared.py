"""Одна нормализация протоколов: алиасы, подписи и политика видимости не расходятся."""

from __future__ import annotations

from app.services.admin_notify import _mini_protocol_label, _protocol_emoji
from app.services.protocols import (
    CANONICAL_PROTOCOLS,
    PROTOCOL_ALIASES,
    PROTOCOL_BADGES,
    PROTOCOL_MODULE_LABELS,
    normalize_protocol,
    protocol_badge,
    protocol_label,
    protocol_module_label,
)
from app.services.vpn_profile_visibility import PROTOCOLS


def test_every_alias_normalizes_to_a_canonical_protocol() -> None:
    for alias in PROTOCOL_ALIASES:
        assert normalize_protocol(alias) in CANONICAL_PROTOCOLS


def test_aliases_are_case_and_space_insensitive() -> None:
    assert normalize_protocol(" OVPN ") == "openvpn"
    assert normalize_protocol("WG") == "wireguard"
    assert normalize_protocol("awg2") == "amneziawg2"


def test_brand_aliases_map_to_the_right_generation() -> None:
    assert normalize_protocol("amneziawg 2.0") == "amneziawg2"
    assert normalize_protocol("wg 2.0") == "amneziawg2"
    assert normalize_protocol("awg 1.5") == "amneziawg"
    assert normalize_protocol("wg/awg 1.5") == "amneziawg"
    assert normalize_protocol("awg") == "amneziawg"


def test_badges_share_one_label_for_wireguard_and_stock_amneziawg() -> None:
    assert PROTOCOL_BADGES["wireguard"] == "WG/AWG 1.5"
    assert PROTOCOL_BADGES["amneziawg"] == "WG/AWG 1.5"
    assert protocol_badge("wireguard") == "WG/AWG 1.5"
    assert protocol_badge("amneziawg") == "WG/AWG 1.5"
    assert protocol_badge("amneziawg2") == "AWG 2.0"
    assert protocol_badge("ovpn") == "OpenVPN"


def test_module_labels_are_human_readable() -> None:
    assert PROTOCOL_MODULE_LABELS == {
        "openvpn": "OpenVPN",
        "wireguard": "WireGuard",
        "amneziawg": "AmneziaWG 1.5",
        "amneziawg2": "AWG 2.0",
    }
    assert protocol_module_label("awg") == "AmneziaWG 1.5"
    assert protocol_module_label("awg2") == "AWG 2.0"


def test_unknown_protocol_falls_back_to_the_normalized_key() -> None:
    assert protocol_label("ipsec") == "ipsec"
    assert protocol_label("  ") == ""
    assert protocol_badge("ipsec") == "ipsec"


def test_amneziawg2_is_not_collapsed_into_amneziawg() -> None:
    assert protocol_label("awg2") == "AmneziaWG 2.0"
    assert _mini_protocol_label("amneziawg2") == "AmneziaWG 2.0"
    assert _protocol_emoji("amneziawg2") == "🌀"


def test_visibility_policy_uses_the_canonical_set() -> None:
    assert PROTOCOLS == CANONICAL_PROTOCOLS
