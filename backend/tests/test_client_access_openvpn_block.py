"""OpenVPN block API routes (ported from AdminAntizapret config_routes_openvpn_block)."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client(env):
    return TestClient(env["app"])


def test_openvpn_temp_block(api_test_env):
    mock_svc = MagicMock()
    mock_svc.openvpn_temp_block.return_value = {"block_until": "2026-06-15T00:00:00Z"}

    with patch("app.routers.client_access._service", return_value=mock_svc), patch(
        "app.routers.client_access.admin_notify_service.send_client_ban"
    ):
        response = _client(api_test_env).post(
            "/api/client-access/openvpn/temp-block",
            json={"client_name": "alice", "days": 7},
            headers=api_test_env["admin_headers"],
        )

    assert response.status_code == 200
    mock_svc.openvpn_temp_block.assert_called_once()
    assert mock_svc.openvpn_temp_block.call_args.args[0] == "alice"
    assert mock_svc.openvpn_temp_block.call_args.args[1] == 7


def test_openvpn_temp_block_requires_days(api_test_env):
    response = _client(api_test_env).post(
        "/api/client-access/openvpn/temp-block",
        json={"client_name": "alice"},
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 400


def test_openvpn_permanent_block(api_test_env):
    mock_svc = MagicMock()
    mock_svc.openvpn_permanent_block.return_value = {"is_blocked": True}

    with patch("app.routers.client_access._service", return_value=mock_svc), patch(
        "app.routers.client_access.admin_notify_service.send_client_ban"
    ):
        response = _client(api_test_env).post(
            "/api/client-access/openvpn/permanent-block",
            json={"client_name": "alice"},
            headers=api_test_env["admin_headers"],
        )

    assert response.status_code == 200
    mock_svc.openvpn_permanent_block.assert_called_once_with("alice", actor="api_admin")


def test_openvpn_unblock(api_test_env):
    mock_svc = MagicMock()
    mock_svc.openvpn_unblock.return_value = {"is_blocked": False}

    with patch("app.routers.client_access._service", return_value=mock_svc), patch(
        "app.routers.client_access.admin_notify_service.send_client_ban"
    ):
        response = _client(api_test_env).post(
            "/api/client-access/openvpn/unblock",
            json={"client_name": "alice"},
            headers=api_test_env["admin_headers"],
        )

    assert response.status_code == 200
    mock_svc.openvpn_unblock.assert_called_once_with("alice", actor="api_admin")
