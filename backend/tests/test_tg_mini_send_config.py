"""Telegram Mini App send-config delivery target (Phase 0)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models import AppSetting, User, VpnConfig, VpnType


def _client(env):
    return TestClient(env["app"])


def _setup_config(env, *, username: str, telegram_id: str | None = None, chat_id: str = ""):
    session = env["session_factory"]()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.telegram_id = telegram_id
        session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
        if chat_id:
            session.add(AppSetting(key="telegram_chat_id", value=chat_id))
        config = VpnConfig(
            node_id=env["node"].id,
            client_name="mini-client",
            vpn_type=VpnType.openvpn,
            owner_id=user.id,
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        return config.id
    finally:
        session.close()


def test_send_config_uses_user_telegram_id(api_test_env):
    config_id = _setup_config(api_test_env, username="api_admin", telegram_id="999888")

    env = api_test_env
    mock_adapter = env["mock_adapter"]
    mock_adapter.get_profile_files.return_value = [
        {
            "protocol": "openvpn",
            "variant": "antizapret",
            "filename": "mini-client.ovpn",
            "path": "/tmp/mini-client.ovpn",
        }
    ]
    mock_adapter.read_profile_file.return_value = "client-config"

    sent: list[tuple[str, str]] = []

    def _capture_send(token, chat_id, path, **kwargs):
        sent.append((token, chat_id))
        return True

    with (
        patch("app.services.telegram_config_send.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.tg_mini.get_active_node", return_value=env["node"]),
        patch("app.services.telegram_config_send.send_tg_document", side_effect=_capture_send),
    ):
        response = _client(env).post(
            f"/api/tg-mini/configs/{config_id}/send",
            json={"destination": "self"},
            headers=env["admin_headers"],
        )

    assert response.status_code == 200
    assert len(sent) == 1
    assert sent[0] == ("test-bot-token", "999888")


def test_send_config_admin_fallback_to_chat_id(api_test_env):
    config_id = _setup_config(api_test_env, username="api_admin", telegram_id=None, chat_id="-100123")

    env = api_test_env
    mock_adapter = env["mock_adapter"]
    mock_adapter.get_profile_files.return_value = [
        {
            "protocol": "openvpn",
            "variant": "antizapret",
            "filename": "mini-client.ovpn",
            "path": "/tmp/mini-client.ovpn",
        }
    ]
    mock_adapter.read_profile_file.return_value = "client-config"

    sent: list[str] = []

    def _capture_send(token, chat_id, path, **kwargs):
        sent.append(chat_id)
        return True

    with (
        patch("app.services.telegram_config_send.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.tg_mini.get_active_node", return_value=env["node"]),
        patch("app.services.telegram_config_send.send_tg_document", side_effect=_capture_send),
    ):
        response = _client(env).post(
            f"/api/tg-mini/configs/{config_id}/send",
            json={"destination": "self"},
            headers=env["admin_headers"],
        )

    assert response.status_code == 200
    assert sent == ["-100123"]


def test_send_config_user_without_telegram_id_fails(api_test_env):
    config_id = _setup_config(api_test_env, username="api_viewer", telegram_id=None)

    env = api_test_env
    mock_adapter = env["mock_adapter"]
    mock_adapter.get_profile_files.return_value = [
        {
            "protocol": "openvpn",
            "variant": "antizapret",
            "filename": "mini-client.ovpn",
            "path": "/tmp/mini-client.ovpn",
        }
    ]
    mock_adapter.read_profile_file.return_value = "client-config"

    with (
        patch("app.services.telegram_config_send.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.tg_mini.get_active_node", return_value=env["node"]),
    ):
        response = _client(env).post(
            f"/api/tg-mini/configs/{config_id}/send",
            json={"destination": "self"},
            headers=env["viewer_headers"],
        )
    assert response.status_code == 503
    assert "Telegram ID" in response.json()["detail"]
