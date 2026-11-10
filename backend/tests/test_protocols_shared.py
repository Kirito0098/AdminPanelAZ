"""Одна нормализация протоколов: алиасы, подписи и политика видимости не расходятся."""

from __future__ import annotations

from app.services.admin_notify import _mini_protocol_label, _protocol_emoji
from app.services.protocols import (
    CANONICAL_PROTOCOLS,
    PROTOCOL_ALIASES,
    normalize_protocol,
    protocol_label,
)
from app.services.vpn_profile_visibility import PROTOCOLS


def test_every_alias_normalizes_to_a_canonical_protocol() -> None:
    for alias in PROTOCOL_ALIASES:
        assert normalize_protocol(alias) in CANONICAL_PROTOCOLS


def test_aliases_are_case_and_space_insensitive() -> None:
    assert normalize_protocol(" OVPN ") == "openvpn"
    assert normalize_protocol("WG") == "wireguard"
    assert normalize_protocol("awg2") == "amneziawg2"


def test_amneziawg2_is_not_collapsed_into_amneziawg() -> None:
    assert protocol_label("awg2") == "AmneziaWG 2.0"
    assert _mini_protocol_label("amneziawg2") == "AmneziaWG 2.0"
    assert _protocol_emoji("amneziawg2") == "🌀"


def test_visibility_policy_uses_the_canonical_set() -> None:
    assert PROTOCOLS == CANONICAL_PROTOCOLS
