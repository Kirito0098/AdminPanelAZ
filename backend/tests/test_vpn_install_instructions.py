"""Install instruction builders for Telegram config delivery."""

from app.services.vpn_install_instructions import (
    build_install_instruction_message,
    normalize_protocol,
)


def test_normalize_awg2_aliases():
    assert normalize_protocol("amneziawg2") == "amneziawg2"
    assert normalize_protocol("AWG2") == "amneziawg2"
    assert normalize_protocol("awg 2.0") == "amneziawg2"


def test_awg2_windows_conf_prefers_amneziawg():
    msg = build_install_instruction_message(
        protocol="amneziawg2",
        platform="windows",
        client_name="terst1",
        filename="AWG2-VPN-terst1.conf",
    )
    assert msg is not None
    assert "AWG 2.0" in msg
    assert "terst1" in msg
    assert "Установите <b>AmneziaWG</b>" in msg
    assert "AmneziaVPN не обязателен" in msg
    # Primary install step must not push AmneziaVPN for .conf
    install_step = msg.split("\n")[3]
    assert "AmneziaWG" in install_step
    assert "AmneziaVPN" not in install_step


def test_awg2_conf_format_tip():
    msg = build_install_instruction_message(
        protocol="amneziawg2",
        platform="android",
        client_name="terst1",
        filename="AWG2-VPN-terst1.conf",
    )
    assert msg is not None
    assert ".conf" in msg
    assert "AmneziaWG" in msg


def test_awg2_vpn_format_uses_amneziavpn():
    msg = build_install_instruction_message(
        protocol="amneziawg2",
        platform="windows",
        client_name="terst1",
        path="/opt/antizapret-awg/clients/vpn/vpn-terst1.vpn",
    )
    assert msg is not None
    assert ".vpn" in msg
    assert "Установите <b>AmneziaVPN</b>" in msg
    assert "не AmneziaWG" in msg


def test_all_os_awg_conf_lead_with_amneziawg():
    for platform in ("ios", "android", "mac", "windows", "linux"):
        for protocol in ("amneziawg", "amneziawg2"):
            msg = build_install_instruction_message(
                protocol=protocol,
                platform=platform,  # type: ignore[arg-type]
                client_name="alice",
                filename="profile.conf",
            )
            assert msg is not None, platform
            assert "Установите <b>AmneziaWG</b>" in msg, (protocol, platform)


def test_unknown_protocol_returns_none():
    assert (
        build_install_instruction_message(
            protocol="shadowsocks",
            platform="ios",
            client_name="x",
        )
        is None
    )


def test_stock_amneziawg_still_works():
    msg = build_install_instruction_message(
        protocol="amneziawg",
        platform="ios",
        client_name="alice",
        filename="AWG-VPN-alice.conf",
    )
    assert msg is not None
    assert "AmneziaWG" in msg
    assert ".conf" in msg
    assert "Установите <b>AmneziaWG</b>" in msg
