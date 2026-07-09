from unittest.mock import MagicMock

from fastapi import HTTPException

from app.services.node_sync.openvpn_restart import restart_all_openvpn_servers


def test_restart_all_openvpn_servers_restarts_installed_units():
    adapter = MagicMock()
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
