"""Telegram bot webhook and link-code tests (Phase 2)."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.models import AppSetting, User, VpnConfig, VpnType


def _client(env):
    return TestClient(env["app"])


def _setup_bot(session_factory, *, secret: str = "test-webhook-secret", interactive: bool = True):
    session = session_factory()
    try:
        session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
        session.add(AppSetting(key="telegram_bot_interactive_enabled", value="true" if interactive else "false"))
        session.add(AppSetting(key="telegram_webhook_secret", value=secret))
        admin = session.query(User).filter(User.username == "api_admin").first()
        admin.telegram_id = "123456789"
        session.commit()
    finally:
        session.close()


def _start_update(chat_id: int = 123456789, user_id: int = 123456789) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "text": "/start",
            "date": 1700000000,
        },
    }


def _status_update(user_id: int = 123456789) -> dict:
    update = _start_update(user_id=user_id)
    update["message"]["text"] = "/status"
    return update


def _link_update(code: str, user_id: int = 999888777) -> dict:
    update = _start_update(user_id=user_id)
    update["message"]["text"] = f"/link {code}"
    return update


def _callback_update(
    data: str,
    *,
    user_id: int = 123456789,
    chat_id: int = 123456789,
    message_id: int = 42,
) -> dict:
    """Telegram Update with callback_query and inline keyboard message."""
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb-query-1",
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "message": {
                "message_id": message_id,
                "from": {"id": 0, "is_bot": True, "first_name": "Bot"},
                "chat": {"id": chat_id, "type": "private"},
                "date": 1700000000,
                "text": "Menu",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "❓ Помощь", "callback_data": "help"}],
                        [{"text": "◀️", "callback_data": "configs:0"}, {"text": "▶️", "callback_data": "configs:1"}],
                    ]
                },
            },
            "chat_instance": "test-instance",
            "data": data,
        },
    }


def _settings_callback_update(user_id: int = 123456789) -> dict:
    return _callback_update("st:root", user_id=user_id)


def _configs_page_callback_update(page: int = 0, user_id: int = 123456789) -> dict:
    return _callback_update(f"configs:{page}", user_id=user_id)


def test_webhook_rejects_wrong_secret(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    with patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True):
        response = _client(api_test_env).post(
            "/api/telegram/webhook/wrong-secret",
            json=_start_update(),
        )
    assert response.status_code == 403


def test_webhook_rejects_non_telegram_ip(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    with patch("app.routers.telegram_webhook.is_telegram_ip", return_value=False):
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_start_update(),
        )
    assert response.status_code == 403


def test_webhook_start_linked_user(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    mock_adapter = api_test_env["mock_adapter"]
    mock_adapter.parse_openvpn_status.return_value = []
    mock_adapter.parse_wireguard_status.return_value = []
    mock_adapter.get_server_ip.return_value = "10.0.0.1"

    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot_handlers.start.send_message", new_callable=AsyncMock) as send,
    ):
        send.return_value = True
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_start_update(),
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    send.assert_awaited_once()


def test_webhook_status_for_linked_user(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    mock_adapter = api_test_env["mock_adapter"]
    mock_adapter.parse_openvpn_status.return_value = []
    mock_adapter.parse_wireguard_status.return_value = []
    mock_adapter.get_server_ip.return_value = "10.0.0.1"

    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot_handlers.status.send_message", new_callable=AsyncMock) as send,
    ):
        send.return_value = True
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_status_update(),
        )
    assert response.status_code == 200
    send.assert_awaited_once()
    text = send.call_args.args[2]
    assert "Статус панели" in text


def test_webhook_link_redeems_code(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    session = api_test_env["session_factory"]()
    try:
        admin = session.query(User).filter(User.username == "api_admin").first()
        admin.telegram_id = None
        session.commit()
        from app.services.telegram_link import create_link_code

        code, _ = create_link_code(session, admin)
    finally:
        session.close()

    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot_handlers.link.send_message", new_callable=AsyncMock) as send,
    ):
        send.return_value = True
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_link_update(code, user_id=999888777),
        )
    assert response.status_code == 200
    send.assert_awaited_once()

    session = api_test_env["session_factory"]()
    try:
        admin = session.query(User).filter(User.username == "api_admin").first()
        assert admin.telegram_id == "999888777"
    finally:
        session.close()


def test_webhook_ignored_when_interactive_disabled(api_test_env):
    _setup_bot(api_test_env["session_factory"], interactive=False)
    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot.telegram_bot_service.handle_update", new_callable=AsyncMock) as handle,
    ):
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_start_update(),
        )
    assert response.status_code == 200
    handle.assert_not_awaited()


def test_link_code_endpoint(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
        session.commit()
    finally:
        session.close()

    response = _client(api_test_env).get("/api/telegram/link-code", headers=api_test_env["admin_headers"])
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["code"]) >= 6
    assert payload["expires_in_seconds"] == 600


def test_register_webhook_endpoint(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
        session.add(AppSetting(key="telegram_bot_interactive_enabled", value="true"))
        session.commit()
    finally:
        session.close()

    with patch("app.routers.maintenance.set_webhook_sync", return_value=(True, "")):
        response = _client(api_test_env).post(
            "/api/settings/telegram/webhook/register",
            headers=api_test_env["admin_headers"],
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["webhook_registered"] is True
    assert payload["webhook_secret_set"] is True


def test_delete_webhook_endpoint(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
        session.add(AppSetting(key="telegram_webhook_set_at", value="2026-01-01T00:00:00+00:00"))
        session.commit()
    finally:
        session.close()

    with patch("app.routers.maintenance.delete_webhook_sync", return_value=(True, "")):
        response = _client(api_test_env).delete(
            "/api/settings/telegram/webhook",
            headers=api_test_env["admin_headers"],
        )
    assert response.status_code == 200
    assert response.json()["webhook_registered"] is False


def test_webhook_callback_help(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot.answer_callback_query", new_callable=AsyncMock) as answer_cb,
        patch("app.services.telegram_bot_handlers.help.edit_message_text", new_callable=AsyncMock) as edit,
    ):
        edit.return_value = True
        answer_cb.return_value = True
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_callback_update("help"),
        )
    assert response.status_code == 200
    answer_cb.assert_awaited_once()
    edit.assert_awaited_once()
    assert "Команды бота" in edit.call_args.args[3]


def test_webhook_callback_settings_root(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot.answer_callback_query", new_callable=AsyncMock) as answer_cb,
        patch("app.services.telegram_bot_handlers.settings.edit_message_text", new_callable=AsyncMock) as edit,
    ):
        edit.return_value = True
        answer_cb.return_value = True
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_settings_callback_update(),
        )
    assert response.status_code == 200
    answer_cb.assert_awaited_once()
    edit.assert_awaited_once()
    text = edit.call_args.args[3]
    assert "Настройки панели" in text
    markup = edit.call_args.kwargs.get("reply_markup") or edit.call_args.args[4]
    assert "inline_keyboard" in markup


def test_webhook_callback_configs_pagination(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    session = api_test_env["session_factory"]()
    try:
        admin = session.query(User).filter(User.username == "api_admin").first()
        session.add(
            VpnConfig(
                node_id=api_test_env["node"].id,
                client_name="bot-client",
                vpn_type=VpnType.openvpn,
                owner_id=admin.id,
            )
        )
        session.commit()
    finally:
        session.close()
    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot.answer_callback_query", new_callable=AsyncMock) as answer_cb,
        patch("app.services.telegram_bot_handlers.configs.edit_message_text", new_callable=AsyncMock) as edit,
    ):
        edit.return_value = True
        answer_cb.return_value = True
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_configs_page_callback_update(0),
        )
    assert response.status_code == 200
    answer_cb.assert_awaited_once()
    edit.assert_awaited_once()
    assert "Конфигурации" in edit.call_args.args[3]


def test_webhook_cidr_status_command(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    update = _start_update()
    update["message"]["text"] = "/cidr"
    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot_handlers.cidr_status.send_message", new_callable=AsyncMock) as send,
        patch(
            "app.services.telegram_bot_handlers.cidr_status._format_cidr_status",
            return_value="🗂 <b>CIDR pipeline</b>\n\nВсего CIDR: <code>0</code>",
        ),
    ):
        send.return_value = True
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=update,
        )
    assert response.status_code == 200
    send.assert_awaited_once()
    assert "CIDR" in send.call_args.args[2]


def test_webhook_rejects_spoofed_forwarded_for(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    update = _start_update()
    with patch("app.routers.telegram_webhook.is_telegram_ip", return_value=False) as is_tg:
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=update,
            headers={
                "X-Forwarded-For": "149.154.167.99",
                "X-Real-IP": "203.0.113.50",
            },
        )
    assert response.status_code == 403
    is_tg.assert_called_once_with("203.0.113.50")


def test_webhook_warper_status_command(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    mock_adapter = api_test_env["mock_adapter"]
    mock_adapter.get_warper_status.return_value = {"status": "running"}
    update = _start_update()
    update["message"]["text"] = "/warper"
    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot_handlers.warper_status.send_message", new_callable=AsyncMock) as send,
    ):
        send.return_value = True
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=update,
        )
    assert response.status_code == 200
    send.assert_awaited_once()
    assert "AZ-WARP" in send.call_args.args[2]
