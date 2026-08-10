"""AZ-AWG2 wave 3b — Telegram bot status payload + handler guards."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

from app.services import tg_mini_status
from app.services.telegram_bot_handlers import awg2_status as awg2_handler
from app.services import telegram_bot_i18n as i18n


def test_build_awg2_payload_not_installed():
    node = SimpleNamespace(id=1, name="local", host="127.0.0.1")
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {
        "installed": False,
        "missing_components": ["awg_client", "overlay_dir"],
        "install_command": "bash <(curl …)",
    }
    adapter.get_awg2_monitoring.side_effect = RuntimeError("not installed")

    with (
        patch.object(tg_mini_status, "get_active_node", return_value=node),
        patch.object(tg_mini_status, "get_active_adapter", return_value=adapter),
    ):
        payload = tg_mini_status.build_awg2_status_payload(MagicMock())

    assert payload["installed"] is False
    assert "awg_client" in payload["missing_components"]
    assert payload["online_count"] == 0
    assert payload["peer_count"] == 0
    assert payload["top_traffic"] == []
    assert payload["install_command"]
    assert payload["node_name"] == "local"


def test_build_awg2_payload_online_and_top_traffic():
    node = SimpleNamespace(id=2, name="vpn-a", host="10.0.0.1")
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {
        "installed": True,
        "missing_components": [],
        "install_command": "bash <(curl …)",
    }
    adapter.get_awg2_monitoring.return_value = {
        "ifaces": [
            {"name": "antizapret-awg", "peer_count": 2},
            {"name": "vpn-awg", "peer_count": 1},
        ],
        "clients": [
            {"name": "low", "online": False, "rx": 10, "tx": 10},
            {"name": "ivan", "online": True, "rx": 1000, "tx": 2000},
            {"name": "petr", "online": True, "rx": 500, "tx": 100},
            {"name": "top", "online": False, "rx": 9000, "tx": 1000},
            {"name": "mid", "online": False, "rx": 3000, "tx": 0},
        ],
        "stats_available": True,
    }

    with (
        patch.object(tg_mini_status, "get_active_node", return_value=node),
        patch.object(tg_mini_status, "get_active_adapter", return_value=adapter),
    ):
        payload = tg_mini_status.build_awg2_status_payload(MagicMock())

    assert payload["installed"] is True
    assert payload["online_count"] == 2
    assert payload["peer_count"] == 5
    assert [row["name"] for row in payload["top_traffic"]] == ["top", "ivan", "mid"]
    assert "antizapret-awg" in payload["ifaces_summary"]
    assert payload["health_error"] is None


def test_handle_awg2_disabled_when_toggle_off():
    ctx = SimpleNamespace(
        user=SimpleNamespace(id=1, role="admin"),
        bot_token="token",
        chat_id=42,
        db=MagicMock(),
        telegram_user_id="99",
        mini_app_url="",
    )
    feature = MagicMock()
    feature.is_enabled.return_value = False
    send = AsyncMock()

    with (
        patch.object(awg2_handler, "get_feature_service", return_value=feature),
        patch.object(awg2_handler, "is_admin", return_value=True),
        patch("app.services.telegram_api.send_message", send),
    ):
        asyncio.run(awg2_handler.handle_awg2_status(ctx))

    send.assert_awaited_once()
    assert send.await_args.args[2] == i18n.AWG2_DISABLED
    feature.is_enabled.assert_called_with("awg2")


def test_mini_awg2_status_404_when_toggle_off():
    from fastapi import HTTPException

    from app.routers import tg_mini as tg_mini_router

    feature = MagicMock()
    feature.is_enabled.return_value = False
    with patch.object(tg_mini_router, "get_feature_service", return_value=feature):
        try:
            tg_mini_router.mini_awg2_status(db=MagicMock(), _=SimpleNamespace())
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 404
            assert "AZ-AWG2" in str(exc.detail)
    feature.is_enabled.assert_called_with("awg2")
