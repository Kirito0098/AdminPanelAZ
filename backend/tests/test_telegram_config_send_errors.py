"""Config send surfaces Telegram network errors from send_tg_document."""

from __future__ import annotations

import io
import urllib.error
from unittest.mock import MagicMock, patch

from app.models import User, UserRole, VpnConfig, VpnType
from app.services.telegram_config_send import send_config_for_user


def test_send_config_for_user_returns_connect_error_on_timeout():
    db = MagicMock()
    user = User(
        username="user1",
        password_hash="hash",
        role=UserRole.user,
        telegram_id="123456789",
    )
    config = VpnConfig(
        node_id=1,
        client_name="client1",
        vpn_type=VpnType.openvpn,
        owner_id=1,
    )

    adapter = MagicMock()
    adapter.get_profile_files.return_value = [
        {
            "path": "/x/client.ovpn",
            "protocol": "openvpn",
            "filename": "client.ovpn",
        }
    ]

    with (
        patch(
            "app.services.telegram_config_send.get_active_adapter",
            return_value=adapter,
        ),
        patch(
            "app.services.telegram_config_send.load_node_remote_hosts",
            return_value=[],
        ),
        patch(
            "app.services.telegram_config_send.read_profile_file_for_delivery",
            return_value="client\n",
        ),
        patch("app.services.telegram._outbound_enabled", return_value=True),
        patch(
            "app.services.telegram.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ),
    ):
        sent, error = send_config_for_user(
            db,
            config,
            user,
            bot_token="test-token",
            run_async=False,
        )

    assert sent == 0
    assert error is not None
    assert "api.telegram.org" in error
    assert "истекло время ожидания" in error


def test_send_tg_document_result_surfaces_telegram_api_description(tmp_path):
    from app.services.telegram import send_tg_document_result

    path = tmp_path / "client.ovpn"
    path.write_text("client\n", encoding="utf-8")

    fp = io.BytesIO(b'{"ok":false,"description":"Bad Request: chat not found"}')
    http_err = urllib.error.HTTPError(
        url="https://api.telegram.org/botx/sendDocument",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=fp,
    )

    with (
        patch("app.services.telegram._outbound_enabled", return_value=True),
        patch("app.services.telegram.urllib.request.urlopen", side_effect=http_err),
    ):
        ok, error = send_tg_document_result(
            "tok",
            "1",
            str(path),
            run_async=False,
            content_type="application/octet-stream",
        )

    assert ok is False
    assert error is not None
    assert "chat not found" in error
