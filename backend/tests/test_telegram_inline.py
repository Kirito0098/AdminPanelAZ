"""Tests for Telegram bot inline query mode (10.4)."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.models import AppSetting, User, VpnConfig, VpnType
from app.services.telegram_bot_handlers.base import BotContext
from app.services.telegram_bot_handlers.inline import build_inline_results, handle_inline_query
from app.services.telegram_bot_inline_cache import (
    clear_inline_results_cache,
    get_cached_inline_results,
    inline_results_cache_key,
)
from app.services.telegram_bot_data import search_user_configs
from tests.conftest import run_async
from tests.test_telegram_bot_settings import _admin_ctx


def _inline_query_update(query: str = "test", user_id: int = 123456789) -> dict:
    return {
        "update_id": 50,
        "inline_query": {
            "id": "inline-query-1",
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "query": query,
            "offset": "",
            "chat_type": "private",
        },
    }


def _chosen_inline_update(result_id: str, user_id: int = 123456789) -> dict:
    return {
        "update_id": 51,
        "chosen_inline_result": {
            "result_id": result_id,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "query": "client",
        },
    }


def test_search_user_configs_partial_match(api_test_env):
    db = api_test_env["session_factory"]()
    try:
        ctx = _admin_ctx(db)
        for name in ("alpha-client", "beta-client", "gamma"):
            db.add(
                VpnConfig(
                    node_id=api_test_env["node"].id,
                    client_name=name,
                    vpn_type=VpnType.openvpn,
                    owner_id=ctx.user.id,
                )
            )
        db.commit()

        matched = search_user_configs(db, ctx.user, "client")
        names = {item.client_name for item in matched}
        assert names == {"alpha-client", "beta-client"}
    finally:
        db.close()


def test_build_inline_results_unlinked():
    ctx = BotContext(
        db=MagicMock(),
        bot_token="token",
        chat_id="1",
        telegram_user_id="1",
        user=None,
        mini_app_url="https://panel.example/api/tg-mini",
    )
    results = build_inline_results(ctx, "anything")
    assert len(results) == 1
    assert results[0]["id"] == "unlinked"
    assert results[0]["type"] == "article"


def test_build_inline_results_includes_mini_app_and_config(api_test_env):
    db = api_test_env["session_factory"]()
    try:
        ctx = _admin_ctx(db)
        config = VpnConfig(
            node_id=api_test_env["node"].id,
            client_name="inline-demo",
            vpn_type=VpnType.openvpn,
            owner_id=ctx.user.id,
        )
        db.add(config)
        db.commit()

        mock_files = [
            {
                "protocol": "openvpn",
                "variant": "vpn",
                "path": "/tmp/inline-demo.ovpn",
                "filename": "inline-demo.ovpn",
            }
        ]
        with (
            patch(
                "app.services.telegram_bot_handlers.inline.get_active_adapter",
            ) as get_adapter,
            patch(
                "app.services.telegram_bot_handlers.inline._create_download_url",
                return_value="https://panel.example/api/public/qr-download/test-token",
            ),
        ):
            get_adapter.return_value.get_profile_files.return_value = mock_files
            results = build_inline_results(ctx, "")

        ids = {item["id"] for item in results}
        assert "miniapp" in ids
        assert any(item.startswith("cfg:") for item in ids)
        document = next(item for item in results if item["type"] == "document")
        assert document["document_url"].endswith("/test-token")
    finally:
        db.close()


def test_inline_results_cache_reuses_fetcher():
    clear_inline_results_cache()
    calls = {"count": 0}

    def fetcher():
        calls["count"] += 1
        return [{"type": "article", "id": "cached"}]

    key = inline_results_cache_key("42", "demo")
    first = get_cached_inline_results(key, 60, fetcher)
    second = get_cached_inline_results(key, 60, fetcher)
    assert first == second
    assert calls["count"] == 1
    clear_inline_results_cache()


def test_handle_inline_query_answers(api_test_env):
    db = api_test_env["session_factory"]()
    try:
        ctx = _admin_ctx(db)
        with patch(
            "app.services.telegram_bot_handlers.inline.answer_inline_query",
            new_callable=AsyncMock,
        ) as answer:
            answer.return_value = True
            run_async(handle_inline_query(ctx, _inline_query_update("app")["inline_query"]))

        answer.assert_awaited_once()
        kwargs = answer.await_args.kwargs
        args = answer.await_args.args
        assert kwargs["cache_time"] == 60
        assert kwargs["is_personal"] is True
        results = kwargs.get("results") if kwargs.get("results") is not None else args[2]
        assert results
    finally:
        db.close()


def test_webhook_inline_query(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
        session.add(AppSetting(key="telegram_bot_interactive_enabled", value="true"))
        session.add(AppSetting(key="telegram_webhook_secret", value="test-webhook-secret"))
        admin = session.query(User).filter(User.username == "api_admin").first()
        admin.telegram_id = "123456789"
        session.commit()
    finally:
        session.close()

    from fastapi.testclient import TestClient

    client = TestClient(api_test_env["app"])
    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch(
            "app.services.telegram_bot_handlers.inline.answer_inline_query",
            new_callable=AsyncMock,
        ) as answer,
    ):
        answer.return_value = True
        response = client.post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_inline_query_update("app"),
        )

    assert response.status_code == 200
    answer.assert_awaited_once()


def test_webhook_chosen_inline_result_sends_config(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
        session.add(AppSetting(key="telegram_bot_interactive_enabled", value="true"))
        session.add(AppSetting(key="telegram_webhook_secret", value="test-webhook-secret"))
        admin = session.query(User).filter(User.username == "api_admin").first()
        admin.telegram_id = "123456789"
        config = VpnConfig(
            node_id=api_test_env["node"].id,
            client_name="chosen-inline",
            vpn_type=VpnType.openvpn,
            owner_id=admin.id,
        )
        session.add(config)
        session.commit()
        config_id = config.id
    finally:
        session.close()

    from fastapi.testclient import TestClient

    client = TestClient(api_test_env["app"])
    with (
        patch("app.routers.telegram_webhook.is_telegram_ip", return_value=True),
        patch(
            "app.services.telegram_config_send.send_config_for_user",
            return_value=(1, None),
        ) as send_config,
        patch(
            "app.services.telegram_bot_handlers.configs._get_accessible_config",
            new_callable=AsyncMock,
        ) as get_config,
    ):
        get_config.return_value = MagicMock(id=config_id, client_name="chosen-inline")
        response = client.post(
            "/api/telegram/webhook/test-webhook-secret",
            json=_chosen_inline_update(f"cfg:{config_id}"),
        )

    assert response.status_code == 200
    send_config.assert_called_once()
