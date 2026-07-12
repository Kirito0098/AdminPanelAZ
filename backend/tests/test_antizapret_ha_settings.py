from app.services.antizapret_params import (
    ANTIZAPRET_HA_SETTING_EXCLUDE,
    filter_ha_replicable_settings,
)


def test_warp_flags_are_ha_replicable():
    """Built-in AntiZapret Cloudflare WARP flags must sync; they are not AZ-WARP."""
    assert "ANTIZAPRET_WARP" not in ANTIZAPRET_HA_SETTING_EXCLUDE
    assert "VPN_WARP" not in ANTIZAPRET_HA_SETTING_EXCLUDE
    filtered = filter_ha_replicable_settings(
        {
            "ANTIZAPRET_WARP": "y",
            "VPN_WARP": "n",
            "openvpn_host": "vpn.example.com",
        }
    )
    assert filtered == {
        "ANTIZAPRET_WARP": "y",
        "VPN_WARP": "n",
        "openvpn_host": "vpn.example.com",
    }
