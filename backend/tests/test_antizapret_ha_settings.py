"""HA auto-sync exclusions for AntiZapret setup settings (step 0.3)."""

from app.services.antizapret_params import (
    ANTIZAPRET_HA_SETTING_EXCLUDE,
    filter_ha_replicable_settings,
)


def test_ha_setting_exclude_contains_warp_flags_only():
    assert ANTIZAPRET_HA_SETTING_EXCLUDE == frozenset({"ANTIZAPRET_WARP", "VPN_WARP"})


def test_filter_ha_replicable_settings_drops_warp_flags():
    updates = {
        "ANTIZAPRET_WARP": "y",
        "VPN_WARP": "n",
        "route_all": "y",
        "openvpn_host": "vpn.example.com",
        "wireguard_host": "vpn.example.com",
    }

    filtered = filter_ha_replicable_settings(updates)

    assert filtered == {
        "route_all": "y",
        "openvpn_host": "vpn.example.com",
        "wireguard_host": "vpn.example.com",
    }


def test_filter_ha_replicable_settings_keeps_hosts_when_only_hosts_present():
    updates = {"openvpn_host": "vpn.example.com", "wireguard_host": "vpn.example.com"}

    assert filter_ha_replicable_settings(updates) == updates


def test_filter_ha_replicable_settings_empty_input():
    assert filter_ha_replicable_settings({}) == {}
