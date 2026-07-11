from unittest.mock import MagicMock

from fastapi import HTTPException

from app.services.node_sync.openvpn_restart import restart_all_openvpn_servers


def _svc(name: str, active: bool):
    svc = MagicMock()
    svc.name = name
    svc.active = active
    return svc


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


def test_restart_all_openvpn_servers_falls_back_when_status_unavailable():
    adapter = MagicMock()
    adapter.get_service_status.side_effect = RuntimeError("monitoring unavailable")
    adapter.restart_service.side_effect = ["ok", "ok", "ok", "ok"]

    result = restart_all_openvpn_servers(adapter)

    assert result["success"] is True
    assert len(result["restarted"]) == 4
    assert adapter.restart_service.call_count == 4
