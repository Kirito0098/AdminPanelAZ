from unittest.mock import MagicMock

from fastapi import HTTPException

from app.services.node_sync.openvpn_restart import (
    openvpn_units_allowed_by_setup,
    restart_all_openvpn_servers,
)


def _svc(name: str, active: bool):
    svc = MagicMock()
    svc.name = name
    svc.active = active
    return svc


def test_openvpn_units_allowed_skips_disabled_tcp():
    allowed = openvpn_units_allowed_by_setup(
        {"OPENVPN_UDP_ENABLE": "y", "OPENVPN_TCP_ENABLE": "n", "WIREGUARD_ENABLE": "y"}
    )
    assert allowed == [
        "openvpn-server@antizapret-udp",
        "openvpn-server@vpn-udp",
    ]


def test_restart_all_openvpn_servers_restarts_only_active_units():
    adapter = MagicMock()
    adapter.get_service_status.return_value = [
        _svc("openvpn-server@antizapret-udp", True),
        _svc("openvpn-server@antizapret-tcp", False),
        _svc("openvpn-server@vpn-udp", True),
        _svc("openvpn-server@vpn-tcp", False),
    ]
    adapter.restart_service.side_effect = ["ok", "ok"]

    result = restart_all_openvpn_servers(adapter)

    assert result["success"] is True
    assert result["restarted"] == [
        "openvpn-server@antizapret-udp",
        "openvpn-server@vpn-udp",
    ]
    assert set(result["skipped"]) == {
        "openvpn-server@antizapret-tcp",
        "openvpn-server@vpn-tcp",
    }
    assert result["failed"] == []
    assert adapter.restart_service.call_count == 2


def test_restart_all_openvpn_servers_skips_missing_unit_errors():
    adapter = MagicMock()
    adapter.get_service_status.return_value = [
        _svc("openvpn-server@antizapret-udp", True),
        _svc("openvpn-server@antizapret-tcp", True),
        _svc("openvpn-server@vpn-udp", True),
        _svc("openvpn-server@vpn-tcp", True),
    ]
    adapter.restart_service.side_effect = [
        "ok",
        HTTPException(status_code=500, detail="Unit openvpn-server@antizapret-tcp.service not found."),
        "ok",
        HTTPException(status_code=500, detail="Unit openvpn-server@vpn-tcp.service not found."),
    ]

    result = restart_all_openvpn_servers(adapter)

    assert result["success"] is True
    assert result["restarted"] == [
        "openvpn-server@antizapret-udp",
        "openvpn-server@vpn-udp",
    ]
    assert "openvpn-server@antizapret-tcp" in result["skipped"]
    assert "openvpn-server@vpn-tcp" in result["skipped"]
    assert result["failed"] == []


def test_restart_skips_tcp_when_setup_disables_even_if_status_unavailable():
    """Fallback without systemd status must still honor OPENVPN_TCP_ENABLE=n."""
    adapter = MagicMock()
    adapter.get_service_status.side_effect = RuntimeError("monitoring unavailable")
    adapter.get_antizapret_settings.return_value = {
        "OPENVPN_UDP_ENABLE": "y",
        "OPENVPN_TCP_ENABLE": "n",
        "WIREGUARD_ENABLE": "y",
    }
    adapter.restart_service.side_effect = ["ok", "ok"]

    result = restart_all_openvpn_servers(adapter)

    assert result["success"] is True
    assert result["restarted"] == [
        "openvpn-server@antizapret-udp",
        "openvpn-server@vpn-udp",
    ]
    assert set(result["skipped"]) == {
        "openvpn-server@antizapret-tcp",
        "openvpn-server@vpn-tcp",
    }
    assert adapter.restart_service.call_count == 2


def test_restart_respects_explicit_protocol_flags_over_adapter():
    adapter = MagicMock()
    adapter.get_service_status.side_effect = RuntimeError("unavailable")
    adapter.restart_service.side_effect = ["ok", "ok"]

    result = restart_all_openvpn_servers(
        adapter,
        protocol_flags={
            "OPENVPN_UDP_ENABLE": "y",
            "OPENVPN_TCP_ENABLE": "n",
            "WIREGUARD_ENABLE": "y",
        },
    )

    assert result["restarted"] == [
        "openvpn-server@antizapret-udp",
        "openvpn-server@vpn-udp",
    ]
    adapter.get_antizapret_settings.assert_not_called()


def test_restart_all_openvpn_servers_falls_back_when_status_and_flags_unavailable():
    adapter = MagicMock()
    adapter.get_service_status.side_effect = RuntimeError("monitoring unavailable")
    adapter.get_antizapret_settings.side_effect = RuntimeError("no settings")
    adapter.restart_service.side_effect = ["ok", "ok", "ok", "ok"]

    result = restart_all_openvpn_servers(adapter)

    assert result["success"] is True
    assert len(result["restarted"]) == 4
    assert adapter.restart_service.call_count == 4
