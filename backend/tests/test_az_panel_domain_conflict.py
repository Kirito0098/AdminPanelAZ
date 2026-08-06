from pathlib import Path

from app.services.antizapret_settings import (
    az_host_updates_conflict_with_panel_domain,
    az_hosts_matching_domain,
    format_az_panel_domain_conflict_message,
    normalize_hostname,
    shared_domain_conflicts_with_panel_domain,
)


def test_normalize_hostname_strips_scheme_port_path():
    assert normalize_hostname("HTTPS://VPN.Example.com:443/path") == "vpn.example.com"
    assert normalize_hostname("vpn.example.com.") == "vpn.example.com"
    assert normalize_hostname("") == ""


def test_az_hosts_matching_domain(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text(
        "OPENVPN_HOST=vpn.claymore-it.ru\nWIREGUARD_HOST=vpn.claymore-it.ru\n",
        encoding="utf-8",
    )
    assert az_hosts_matching_domain("VPN.Claymore-IT.ru", setup) == ["vpn.claymore-it.ru"]
    assert az_hosts_matching_domain("panel.claymore-it.ru", setup) == []
    assert format_az_panel_domain_conflict_message("vpn.claymore-it.ru", setup_path=setup)
    assert format_az_panel_domain_conflict_message("panel.claymore-it.ru", setup_path=setup) is None


def test_az_host_updates_conflict_with_panel_domain():
    assert az_host_updates_conflict_with_panel_domain(
        {"openvpn_host": "panel.example.com"},
        "panel.example.com",
    )
    assert (
        az_host_updates_conflict_with_panel_domain(
            {"openvpn_host": "vpn.example.com"},
            "panel.example.com",
        )
        is None
    )
    assert (
        az_host_updates_conflict_with_panel_domain(
            {"ANTIZAPRET_ADBLOCK": "y"},
            "panel.example.com",
        )
        is None
    )


def test_shared_domain_conflicts_with_panel_domain():
    assert shared_domain_conflicts_with_panel_domain("vpn.example.com", "vpn.example.com")
    assert shared_domain_conflicts_with_panel_domain("vpn.example.com", "panel.example.com") is None
