"""Smoke tests for Telegram Mini App v2 API routes."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models import AppSetting, User, VpnConfig, VpnType


def _client(env):
    return TestClient(env["app"])


def _setup_config(env, *, username: str = "api_admin", telegram_id: str | None = "999888"):
    session = env["session_factory"]()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.telegram_id = telegram_id
        session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
        session.add(AppSetting(key="telegram_chat_id", value="-100123"))
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


def test_config_files_returns_enriched_list(api_test_env):
    config_id = _setup_config(api_test_env)
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

    with (
        patch("app.routers.tg_mini.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.tg_mini.get_active_node", return_value=env["node"]),
    ):
        response = _client(env).get(
            f"/api/tg-mini/configs/{config_id}/files",
            headers=env["admin_headers"],
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["files"]) == 1
    assert body["files"][0]["path"] == "/tmp/mini-client.ovpn"
    assert "download_filename" in body["files"][0]


def test_send_config_v2_self_destination(api_test_env):
    config_id = _setup_config(api_test_env, telegram_id="555444")
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
        patch("app.routers.tg_mini.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.tg_mini.get_active_node", return_value=env["node"]),
        patch("app.routers.tg_mini.send_tg_document", side_effect=_capture_send),
    ):
        response = _client(env).post(
            f"/api/tg-mini/configs/{config_id}/send",
            json={"path": "/tmp/mini-client.ovpn", "destination": "self"},
            headers=env["admin_headers"],
        )

    assert response.status_code == 200
    assert sent == ["555444"]


def test_send_config_v2_chat_destination_admin_only(api_test_env):
    config_id = _setup_config(api_test_env, username="api_viewer", telegram_id="111222")
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

    with (
        patch("app.routers.tg_mini.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.tg_mini.get_active_node", return_value=env["node"]),
    ):
        response = _client(env).post(
            f"/api/tg-mini/configs/{config_id}/send",
            json={"destination": "chat"},
            headers=env["viewer_headers"],
        )

    assert response.status_code == 403


def test_qr_link_creates_token(api_test_env):
    config_id = _setup_config(api_test_env)
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

    with (
        patch("app.routers.tg_mini.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.tg_mini.get_active_node", return_value=env["node"]),
    ):
        response = _client(env).get(
            "/api/tg-mini/qr-link",
            params={"config_id": config_id, "path": "/tmp/mini-client.ovpn"},
            headers=env["admin_headers"],
        )

    assert response.status_code == 200
    body = response.json()
    assert "/api/public/qr-download/" in body["url"]
    assert body["max_downloads"] >= 1


def test_admin_notify_proxy_get_and_patch(api_test_env):
    env = api_test_env
    client = _client(env)

    get_response = client.get("/api/tg-mini/admin-notify", headers=env["admin_headers"])
    assert get_response.status_code == 200
    assert "events" in get_response.json()

    patch_response = client.patch(
        "/api/tg-mini/admin-notify",
        json={"events": {"login_success": False}},
        headers=env["admin_headers"],
    )
    assert patch_response.status_code == 200
    events = {item["key"]: item["enabled"] for item in patch_response.json()["events"]}
    assert events["login_success"] is False


def test_admin_notify_rejects_telegram_id_patch(api_test_env):
    env = api_test_env
    response = _client(env).patch(
        "/api/tg-mini/admin-notify",
        json={"telegram_id": "123456789"},
        headers=env["admin_headers"],
    )
    assert response.status_code == 400


def test_mini_app_page_requires_build(api_test_env, monkeypatch, tmp_path):
    env = api_test_env
    index = tmp_path / "index.html"
    index.write_text("<html><body>Mini</body></html>", encoding="utf-8")

    with patch("app.routers.tg_mini._STATIC_DIR", tmp_path):
        response = _client(env).get("/api/tg-mini")

    assert response.status_code == 200
    assert "Mini" in response.text
