"""Telegram bot /nodes command tests."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.models import AppSetting, Node, NodeStatus, User


def _client(env):
    return TestClient(env["app"])


def _setup_bot(session_factory, *, secret: str = "test-webhook-secret"):
    session = session_factory()
    try:
        session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
        session.add(AppSetting(key="telegram_bot_interactive_enabled", value="true"))
        session.add(AppSetting(key="telegram_webhook_secret", value=secret))
        admin = session.query(User).filter(User.username == "api_admin").first()
        admin.telegram_id = "123456789"
        session.commit()
    finally:
        session.close()


def _nodes_update(user_id: int = 123456789) -> dict:
    return {
        "update_id": 3,
        "message": {
            "message_id": 11,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": user_id, "type": "private"},
            "text": "/nodes",
            "date": 1700000000,
        },
    }


def test_webhook_nodes_admin(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot_handlers.nodes.send_message", new_callable=AsyncMock) as send,
    ):
        send.return_value = True
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_nodes_update(),
        )
    assert response.status_code == 200
    send.assert_awaited_once()
    text = send.call_args.args[2]
    assert "VPN-узлы" in text
    markup = send.call_args.kwargs["reply_markup"]
    assert markup["inline_keyboard"]


def test_webhook_nodes_activate_callback(api_test_env):
    _setup_bot(api_test_env["session_factory"])
    session = api_test_env["session_factory"]()
    try:
        remote = Node(
            name="remote-1",
            host="10.0.0.2",
            port=9100,
            api_key_hash="hash",
            api_key_encrypted="enc",
            is_local=False,
            status=NodeStatus.online,
        )
        session.add(remote)
        session.commit()
        session.refresh(remote)
        remote_id = remote.id
    finally:
        session.close()

    update = {
        "update_id": 4,
        "callback_query": {
            "id": "cb-nodes-activate",
            "from": {"id": 123456789, "is_bot": False, "first_name": "Test"},
            "message": {
                "message_id": 55,
                "chat": {"id": 123456789, "type": "private"},
                "date": 1700000000,
                "text": "node",
            },
            "data": f"nda:{remote_id}",
        },
    }

    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch("app.services.telegram_bot_handlers.nodes.check_node_health", return_value={"status": "online"}),
        patch("app.services.telegram_bot_handlers.nodes.edit_message_text", new_callable=AsyncMock) as edit,
        patch("app.services.telegram_api.answer_callback_query", new_callable=AsyncMock) as answer,
    ):
        edit.return_value = True
        answer.return_value = True
        response = _client(api_test_env).post(
            "/api/telegram/webhook/test-webhook-secret",
            json=update,
        )
    assert response.status_code == 200
    edit.assert_awaited_once()
    text = edit.call_args.args[3]
    assert "remote-1" in text

    session = api_test_env["session_factory"]()
    try:
        active = session.query(AppSetting).filter(AppSetting.key == "active_node_id").first()
        assert active is not None
        assert active.value == str(remote_id)
    finally:
        session.close()
