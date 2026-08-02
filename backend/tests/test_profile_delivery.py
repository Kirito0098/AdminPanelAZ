from unittest.mock import MagicMock

from app.services.profile_delivery import read_profile_file_for_delivery

OVPN = "remote 10.0.0.1 1194 udp\n"
WG = "[Interface]\nPrivateKey=x\n"


def test_delivery_patches_ovpn():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = OVPN
    out = read_profile_file_for_delivery(adapter, "/x/client.ovpn", ["1.1.1.1", "2.2.2.2"])
    assert "remote 1.1.1.1 1194 udp" in out
    assert "remote 2.2.2.2 1194 udp" in out


def test_delivery_skips_non_ovpn():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = WG
    out = read_profile_file_for_delivery(adapter, "/x/client.conf", ["1.1.1.1"])
    assert out == WG


def test_delivery_empty_hosts_raw():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = OVPN
    assert read_profile_file_for_delivery(adapter, "/x/a.ovpn", []) == OVPN
