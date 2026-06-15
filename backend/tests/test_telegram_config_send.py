"""Tests for Telegram config file delivery in interactive bot."""

from unittest.mock import AsyncMock, patch

from app.models import VpnConfig, VpnType
from app.services.telegram_bot_handlers.configs import handle_config_callback
from tests.conftest import run_async
from tests.test_telegram_bot_settings import _admin_ctx


def test_handle_config_callback_shows_picker_for_multiple_files(api_test_env):
    db = api_test_env["session_factory"]()
    try:
        ctx = _admin_ctx(db)
        config = VpnConfig(
            node_id=api_test_env["node"].id,
            client_name="fdsd",
            vpn_type=VpnType.openvpn,
            owner_id=ctx.user.id,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        config_id = config.id
    finally:
        db.close()

    mock_files = [
        {"protocol": "openvpn", "variant": "antizapret", "path": "/a.ovpn", "filename": "a.ovpn"},
        {"protocol": "openvpn", "variant": "vpn", "path": "/b.ovpn", "filename": "b.ovpn"},
    ]

    db = api_test_env["session_factory"]()
    try:
        ctx = _admin_ctx(db)
        with (
            patch(
                "app.services.telegram_bot_handlers.configs.get_active_adapter",
            ) as get_adapter,
            patch(
                "app.services.telegram_bot_handlers.configs.send_or_edit",
                new_callable=AsyncMock,
            ) as send_or_edit,
        ):
            adapter = get_adapter.return_value
            adapter.get_profile_files.return_value = mock_files
            send_or_edit.return_value = True
            run_async(handle_config_callback(ctx, config_id))

        send_or_edit.assert_awaited()
        markup = send_or_edit.await_args.kwargs.get("markup") or send_or_edit.await_args.kwargs.get("reply_markup")
        callbacks = [
            btn.get("callback_data")
            for row in markup.get("inline_keyboard", [])
            for btn in row
            if btn.get("callback_data")
        ]
        assert any(item.startswith("cfgg:") for item in callbacks)
    finally:
        db.close()
