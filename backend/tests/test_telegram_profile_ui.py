"""Tests for Telegram profile file grouping."""

from app.services.telegram_profile_ui import (
    build_profile_file_groups,
    file_button_label,
    file_caption,
    protocol_group_key,
)


def test_protocol_group_key_separates_wg_and_awg():
    assert protocol_group_key("wireguard") == "wg"
    assert protocol_group_key("amneziawg") == "awg"
    assert protocol_group_key("openvpn") == "ovpn"


def test_build_profile_file_groups_splits_wg_and_awg():
    files = [
        {"protocol": "wireguard", "variant": "antizapret", "path": "/client/wireguard/antizapret/vpn-x-wg.conf"},
        {"protocol": "wireguard", "variant": "vpn", "path": "/client/wireguard/vpn/vpn-x-wg.conf"},
        {"protocol": "amneziawg", "variant": "antizapret", "path": "/client/amneziawg/antizapret/vpn-x-am.conf"},
        {"protocol": "amneziawg", "variant": "vpn", "path": "/client/amneziawg/vpn/vpn-x-am.conf"},
    ]
    groups = build_profile_file_groups("x", files)
    assert [group.key for group in groups] == ["wg", "awg"]
    assert len(groups[0].files) == 2
    assert len(groups[1].files) == 2


def test_file_button_label_uses_route_and_suffix():
    file_item = {
        "protocol": "openvpn",
        "variant": "antizapret-udp",
        "path": "/client/openvpn/antizapret-udp/vpn-test-udp.ovpn",
        "download_filename": "AZ-test-udp.ovpn",
    }
    assert file_button_label(file_item) == "AZ · UDP"


def test_file_caption_includes_protocol_and_name():
    file_item = {
        "protocol": "amneziawg",
        "variant": "vpn",
        "path": "/client/amneziawg/vpn/vpn-123-am.conf",
        "download_filename": "AWG-VPN-123.conf",
    }
    text = file_caption(client_name="123", file_item=file_item)
    assert "AmneziaWG" in text
    assert "123" in text
    assert "AWG-VPN-123.conf" in text
