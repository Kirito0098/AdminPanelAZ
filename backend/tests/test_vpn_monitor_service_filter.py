"""VPN monitor services respect OPENVPN_*_ENABLE / WIREGUARD_ENABLE from setup."""

from __future__ import annotations

from pathlib import Path

from app.schemas import MonitoringService
from app.services.antizapret_settings import (
    filter_vpn_monitor_services,
    is_vpn_monitor_service_expected,
    read_antizapret_settings,
    read_protocol_enable_flags,
)


def _svc(name: str, active: bool = False) -> MonitoringService:
    return MonitoringService(name=name, status="active" if active else "inactive", active=active)


def test_tcp_disabled_skips_tcp_units():
    settings = {
        "OPENVPN_UDP_ENABLE": "y",
        "OPENVPN_TCP_ENABLE": "n",
        "WIREGUARD_ENABLE": "y",
    }
    assert is_vpn_monitor_service_expected("openvpn-server@antizapret-udp", settings)
    assert not is_vpn_monitor_service_expected("openvpn-server@antizapret-tcp", settings)
    assert not is_vpn_monitor_service_expected("openvpn-server@vpn-tcp", settings)
    assert is_vpn_monitor_service_expected("wg-quick@vpn", settings)


def test_filter_drops_disabled_protocol_units():
    settings = {"OPENVPN_TCP_ENABLE": "n", "OPENVPN_UDP_ENABLE": "y", "WIREGUARD_ENABLE": "n"}
    services = [
        _svc("openvpn-server@antizapret-udp", True),
        _svc("openvpn-server@antizapret-tcp"),
        _svc("openvpn-server@vpn-udp", True),
        _svc("openvpn-server@vpn-tcp"),
        _svc("wg-quick@antizapret"),
        _svc("wg-quick@vpn"),
    ]
    filtered = filter_vpn_monitor_services(services, settings)
    names = [s.name for s in filtered]
    assert names == [
        "openvpn-server@antizapret-udp",
        "openvpn-server@vpn-udp",
    ]


def test_missing_flags_default_to_expected():
    assert is_vpn_monitor_service_expected("openvpn-server@vpn-tcp", {})


def test_read_protocol_enable_flags_from_setup(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text(
        "OPENVPN_UDP_ENABLE=y\nOPENVPN_TCP_ENABLE=n\nWIREGUARD_ENABLE=y\n",
        encoding="utf-8",
    )
    flags = read_protocol_enable_flags(setup)
    assert flags == {
        "OPENVPN_UDP_ENABLE": "y",
        "OPENVPN_TCP_ENABLE": "n",
        "WIREGUARD_ENABLE": "y",
    }
    settings = read_antizapret_settings(setup)
    assert settings["OPENVPN_TCP_ENABLE"] == "n"
    assert settings["OPENVPN_UDP_ENABLE"] == "y"
