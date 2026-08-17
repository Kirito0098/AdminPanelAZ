from unittest.mock import MagicMock

from app.services.profile_delivery import read_profile_file_for_delivery

OVPN = "remote 10.0.0.1 1194 udp\n"
WG = "[Interface]\nPrivateKey=x\n"
SAMPLE = """[Interface]
PrivateKey=abc
[Peer]
Endpoint = 10.0.0.1:51820
AllowedIPs = 0.0.0.0/0
"""


def test_delivery_patches_ovpn():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = OVPN
    out = read_profile_file_for_delivery(adapter, "/x/client.ovpn", ["1.1.1.1", "2.2.2.2"])
    assert "remote 1.1.1.1 1194 udp" in out
    assert "remote 2.2.2.2 1194 udp" in out


def test_delivery_skips_non_ovpn():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = WG
    adapter.get_antizapret_settings.return_value = {"wireguard_host": "9.9.9.9"}
    out = read_profile_file_for_delivery(adapter, "/x/client.conf", ["1.1.1.1"])
    assert out == WG


def test_delivery_empty_hosts_raw():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = OVPN
    assert read_profile_file_for_delivery(adapter, "/x/a.ovpn", []) == OVPN


def test_delivery_patches_awg_from_wireguard_host_not_openvpn_list():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = SAMPLE
    adapter.get_antizapret_settings.return_value = {"wireguard_host": "vpn.example.com"}
    out = read_profile_file_for_delivery(
        adapter, "/client/amneziawg/vpn/client-am.conf", ["9.9.9.9", "8.8.8.8"]
    )
    assert "Endpoint = vpn.example.com:51820" in out
    assert "9.9.9.9" not in out


def test_delivery_skips_wg_patch_when_wireguard_host_empty():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = SAMPLE
    adapter.get_antizapret_settings.return_value = {"wireguard_host": ""}
    out = read_profile_file_for_delivery(
        adapter, "/client/wireguard/vpn/client-wg.conf", ["9.9.9.9"]
    )
    assert out == SAMPLE


def test_delivery_skips_wg_patch_when_settings_fail():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = SAMPLE
    adapter.get_antizapret_settings.side_effect = RuntimeError("node down")
    out = read_profile_file_for_delivery(
        adapter, "/client/amneziawg/antizapret/client-am.conf", ["9.9.9.9"]
    )
    assert out == SAMPLE
