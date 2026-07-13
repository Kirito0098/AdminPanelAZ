"""Unit tests for VPN profile visibility policy resolve/filter."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import UserRole, VpnType
from app.services.vpn_profile_visibility import (
    FULL_POLICY,
    can_create_vpn_type,
    filter_profile_files,
    normalize_policy,
    profile_file_allowed,
    resolve_visible_vpn_profiles,
)


POLICY_A = {
    "routes": ["az", "vpn"],
    "protocols": ["openvpn"],
    "openvpn_groups": ["udp"],
}

POLICY_B = {
    "routes": ["az", "vpn"],
    "protocols": ["openvpn", "wireguard", "amneziawg"],
    "openvpn_groups": ["udp"],
}

SAMPLE_FILES = [
    {"protocol": "openvpn", "variant": "antizapret", "path": "/client/openvpn/antizapret/x.ovpn"},
    {"protocol": "openvpn", "variant": "antizapret-udp", "path": "/client/openvpn/antizapret-udp/x-udp.ovpn"},
    {"protocol": "openvpn", "variant": "antizapret-tcp", "path": "/client/openvpn/antizapret-tcp/x-tcp.ovpn"},
    {"protocol": "openvpn", "variant": "vpn", "path": "/client/openvpn/vpn/x.ovpn"},
    {"protocol": "openvpn", "variant": "vpn-udp", "path": "/client/openvpn/vpn-udp/x-udp.ovpn"},
    {"protocol": "openvpn", "variant": "vpn-tcp", "path": "/client/openvpn/vpn-tcp/x-tcp.ovpn"},
    {"protocol": "wireguard", "variant": "antizapret", "path": "/client/wireguard/antizapret/x-wg.conf"},
    {"protocol": "wireguard", "variant": "vpn", "path": "/client/wireguard/vpn/x-wg.conf"},
    {"protocol": "amneziawg", "variant": "antizapret", "path": "/client/amneziawg/antizapret/x-am.conf"},
    {"protocol": "amneziawg", "variant": "vpn", "path": "/client/amneziawg/vpn/x-am.conf"},
]


class _FakeQuery:
    def __init__(self, value: str | None):
        self._value = value

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        if self._value is None:
            return None
        return SimpleNamespace(value=self._value)


class _FakeDb:
    def __init__(self, setting_value: str | None = None):
        self._setting_value = setting_value

    def query(self, *_args, **_kwargs):
        return _FakeQuery(self._setting_value)


def _user(*, role: UserRole = UserRole.user, visible: str | None = None):
    return SimpleNamespace(role=role, visible_vpn_profiles=visible)


def test_normalize_policy_full_default():
    assert set(normalize_policy(None)["routes"]) == {"az", "vpn"}
    assert set(normalize_policy({})["protocols"]) == set()


def test_normalize_policy_strict_rejects_unknown():
    with pytest.raises(HTTPException) as exc:
        normalize_policy({"routes": ["az"], "protocols": ["openvpn"], "openvpn_groups": ["nope"]}, strict=True)
    assert exc.value.status_code == 400


def test_example_a_only_udp_ovpn():
    allowed = filter_profile_files(SAMPLE_FILES, POLICY_A)
    variants = {(f["protocol"], f["variant"]) for f in allowed}
    assert variants == {("openvpn", "antizapret-udp"), ("openvpn", "vpn-udp")}
    assert can_create_vpn_type(POLICY_A, VpnType.openvpn)
    assert not can_create_vpn_type(POLICY_A, VpnType.wireguard)


def test_example_b_udp_ovpn_plus_wg_awg():
    allowed = filter_profile_files(SAMPLE_FILES, POLICY_B)
    variants = {(f["protocol"], f["variant"]) for f in allowed}
    assert ("openvpn", "antizapret-udp") in variants
    assert ("openvpn", "vpn-udp") in variants
    assert ("wireguard", "antizapret") in variants
    assert ("amneziawg", "vpn") in variants
    assert ("openvpn", "antizapret") not in variants
    assert ("openvpn", "vpn-tcp") not in variants
    assert can_create_vpn_type(POLICY_B, VpnType.openvpn)
    assert can_create_vpn_type(POLICY_B, VpnType.wireguard)


def test_empty_openvpn_groups_hides_ovpn_files():
    policy = {"routes": ["az", "vpn"], "protocols": ["openvpn", "wireguard"], "openvpn_groups": []}
    allowed = filter_profile_files(SAMPLE_FILES, policy)
    assert all(f["protocol"] != "openvpn" for f in allowed)
    assert not can_create_vpn_type(policy, VpnType.openvpn)
    assert can_create_vpn_type(policy, VpnType.wireguard)


def test_admin_gets_full_policy():
    db = _FakeDb('{"routes":["az"],"protocols":["openvpn"],"openvpn_groups":["udp"]}')
    policy = resolve_visible_vpn_profiles(db, _user(role=UserRole.admin))
    assert set(policy["routes"]) == set(FULL_POLICY["routes"])
    assert set(policy["protocols"]) == set(FULL_POLICY["protocols"])


def test_null_inherits_default():
    db = _FakeDb(
        '{"routes":["az","vpn"],"protocols":["openvpn"],"openvpn_groups":["udp"]}'
    )
    policy = resolve_visible_vpn_profiles(db, _user(visible=None))
    assert policy["protocols"] == ["openvpn"]
    assert policy["openvpn_groups"] == ["udp"]


def test_override_replaces_default():
    db = _FakeDb(
        '{"routes":["az","vpn"],"protocols":["openvpn","wireguard","amneziawg"],"openvpn_groups":["udp","tcp"]}'
    )
    override = '{"routes":["az"],"protocols":["wireguard"],"openvpn_groups":[]}'
    policy = resolve_visible_vpn_profiles(db, _user(visible=override))
    assert policy["routes"] == ["az"]
    assert policy["protocols"] == ["wireguard"]
    assert policy["openvpn_groups"] == []


def test_missing_default_is_full():
    db = _FakeDb(None)
    policy = resolve_visible_vpn_profiles(db, _user(visible=None))
    assert set(policy["protocols"]) == set(FULL_POLICY["protocols"])


def test_amneziawg_only_allows_wireguard_create():
    policy = {"routes": ["az", "vpn"], "protocols": ["amneziawg"], "openvpn_groups": []}
    assert can_create_vpn_type(policy, VpnType.wireguard)
    assert profile_file_allowed(
        policy,
        protocol="amneziawg",
        variant="vpn",
        path="/client/amneziawg/vpn/x-am.conf",
    )
    assert not profile_file_allowed(
        policy,
        protocol="wireguard",
        variant="vpn",
        path="/client/wireguard/vpn/x-wg.conf",
    )
