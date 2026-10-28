"""AWG2 download must rewrite Endpoint host like stock AmneziaWG (proxy path)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.profile_delivery import read_profile_file_for_delivery


def test_awg2_conf_endpoint_uses_wireguard_host():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = (
        "[Interface]\nPrivateKey = x\n"
        "[Peer]\nPublicKey = y\nEndpoint = 203.0.113.10:41234\n"
    )
    adapter.get_antizapret_settings.return_value = {"wireguard_host": "198.51.100.7"}

    out = read_profile_file_for_delivery(
        adapter,
        "/opt/antizapret-awg/clients/alice-am.conf",
        hosts=["198.51.100.7", "203.0.113.10"],
    )

    assert "Endpoint = 198.51.100.7:41234" in out
    assert "203.0.113.10:41234" not in out


def test_awg2_without_wireguard_host_keeps_endpoint():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = "Endpoint = 203.0.113.10:41234\n"
    adapter.get_antizapret_settings.return_value = {"wireguard_host": ""}

    out = read_profile_file_for_delivery(
        adapter,
        "/opt/antizapret-awg/clients/alice-am.conf",
        hosts=[],
    )

    assert out == "Endpoint = 203.0.113.10:41234\n"


def test_stock_amneziawg_still_patched():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = "Endpoint = vpn.example:52080\n"
    adapter.get_antizapret_settings.return_value = {"wireguard_host": "proxy.example"}

    out = read_profile_file_for_delivery(
        adapter,
        "/root/antizapret/client/amneziawg/bob-am.conf",
        hosts=["proxy.example"],
    )

    assert "Endpoint = proxy.example:52080" in out
