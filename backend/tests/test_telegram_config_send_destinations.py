"""Configs must never fall back to telegram_chat_id (backup/group chats)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models import User, UserRole, VpnConfig, VpnType
from app.services.telegram_config_send import send_config_for_user

MOD = "app.services.telegram_config_send"


def test_admin_without_telegram_id_does_not_use_backup_chat():
    admin = User(id=1, username="admin", password_hash="x", role=UserRole.admin, telegram_id=None)
    config = VpnConfig(id=3, node_id=1, client_name="ivan", vpn_type=VpnType.wireguard, owner_id=1)
    with (
        patch("app.services.telegram_recipients.get_setting_chat_ids") as get_chats,
        patch(f"{MOD}.send_config_files_to_chat") as send_files,
    ):
        sent, err = send_config_for_user(
            MagicMock(),
            config,
            admin,
            bot_token="token",
            destination="self",
            run_async=False,
        )
    assert sent == 0
    assert err == "Привяжите Telegram"
    get_chats.assert_not_called()
    send_files.assert_not_called()


def test_self_uses_personal_telegram_id_only():
    admin = User(id=1, username="admin", password_hash="x", role=UserRole.admin, telegram_id="999")
    config = VpnConfig(id=3, node_id=1, client_name="ivan", vpn_type=VpnType.wireguard, owner_id=1)
    with (
        patch("app.services.telegram_recipients.get_setting_chat_ids") as get_chats,
        patch(f"{MOD}.send_config_files_to_chat", return_value=(1, None)) as send_files,
    ):
        sent, err = send_config_for_user(
            MagicMock(),
            config,
            admin,
            bot_token="token",
            destination="self",
            run_async=False,
        )
    assert sent == 1
    assert err is None
    get_chats.assert_not_called()
    assert send_files.call_args.kwargs["chat_id"] == "999" or send_files.call_args.args[3] == "999" or True
    # chat_id is a keyword arg in send_config_files_to_chat
    assert send_files.call_args.kwargs.get("chat_id") == "999"
