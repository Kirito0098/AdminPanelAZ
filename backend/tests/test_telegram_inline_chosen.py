import asyncio
from unittest.mock import MagicMock

from app.services.telegram_bot_handlers import inline as inline_mod


def test_chosen_inline_sends_sync_and_reports_error(monkeypatch):
    ctx = MagicMock()
    ctx.user = MagicMock()
    ctx.bot_token = "t"
    ctx.db = MagicMock()
    ctx.telegram_user_id = 1
    config = MagicMock()

    async def fake_get(_ctx, _config_id):
        return config

    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.configs._get_accessible_config",
        fake_get,
    )
    sent = {}

    def fake_send(*_a, **kwargs):
        sent["run_async"] = kwargs.get("run_async")
        return 0, "сеть недоступна"

    messages = []

    def fake_msg(token, chat_id, text, *, run_async=True):
        messages.append((str(chat_id), text, run_async))
        return True

    monkeypatch.setattr(
        "app.services.telegram_config_send.send_config_for_user",
        fake_send,
    )
    monkeypatch.setattr("app.services.telegram.send_tg_message", fake_msg)
    monkeypatch.setattr(inline_mod, "send_tg_message", fake_msg, raising=False)

    chosen = {"result_id": "cfg:9", "from": {"id": 42}}

    asyncio.run(inline_mod.handle_chosen_inline_result(ctx, chosen))

    assert sent["run_async"] is False
    assert messages and messages[0][0] == "42"
    assert "сеть недоступна" in messages[0][1]
    assert messages[0][2] is False
