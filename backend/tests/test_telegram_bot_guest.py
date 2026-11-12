"""Гость без привязки: единый гейт на текстовые «кнопки» и лимит публичных команд."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services import telegram_bot as bot_module
from app.services import telegram_bot_i18n as i18n
from app.services.app_setting_store import _set_setting
from app.services.telegram_bot_handlers import menu, user_renew
from app.services.telegram_bot_handlers.base import BotContext, TelegramBotSettingsSnapshot

_SNAP = TelegramBotSettingsSnapshot(
    bot_token="bot-token",
    interactive_enabled=True,
    bot_username="bot",
    webhook_set_at="",
    webhook_secret_set=True,
    token_set=True,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def sent(monkeypatch, db):
    calls: list[tuple[str, dict]] = []

    async def fake_send(_token, _chat_id, text, **kwargs):
        calls.append((text, kwargs))
        return True

    monkeypatch.setattr(menu, "send_message", fake_send)
    monkeypatch.setattr(bot_module, "load_telegram_bot_settings_snapshot", lambda _db: _SNAP)
    monkeypatch.setattr(bot_module, "resolve_user", lambda _db, _tg: None)
    monkeypatch.setattr(
        bot_module.telegram_bot_command_rate_limit_service, "consume", lambda *_a, **_k: None
    )
    return calls


def _run_text(db, text: str) -> None:
    update = {
        "message": {
            "text": text,
            "from": {"id": 42},
            "chat": {"id": 42, "type": "private"},
        }
    }
    asyncio.run(
        bot_module.TelegramBotService().handle_update(db, update, mini_app_url="https://p/api/tg-mini")
    )


def _run_callback(db, data: str) -> None:
    update = {
        "callback_query": {
            "id": "cb-1",
            "data": data,
            "from": {"id": 42},
            "message": {
                "_did": "m1",
                "message_id": 10,
                "chat": {"id": 42, "type": "private"},
            },
        }
    }
    asyncio.run(
        bot_module.TelegramBotService().handle_update(db, update, mini_app_url="https://p/api/tg-mini")
    )


def _context(db) -> BotContext:
    return BotContext(
        db=db,
        bot_token="bot-token",
        chat_id=42,
        telegram_user_id="42",
        user=None,
        settings=_SNAP,
    )


def _texts(calls: list[tuple[str, dict]]) -> list[str]:
    return [text for text, _ in calls]


def test_guest_admin_button_gets_unlinked_not_admin_only(db, sent):
    _run_text(db, i18n.BTN_MENU_SETTINGS)

    assert _texts(sent) == [i18n.UNLINKED]
    keyboard = sent[0][1]["reply_markup"]["keyboard"]
    assert keyboard[0][0]["text"] == i18n.BTN_MENU_HUB


def test_guest_never_enters_the_redeem_fsm(db, sent, monkeypatch):
    handled = AsyncMock(return_value=True)
    monkeypatch.setattr(user_renew, "try_handle_code_message", handled)
    # Состояние, оставшееся от прошлых версий, не должно перехватить сообщение.
    user_renew._awaiting_code.add("42")
    try:
        _run_text(db, i18n.BTN_REDEEM_UNLOCK)
        _run_text(db, "SECRET-CODE")

        assert _texts(sent) == [i18n.UNLINKED, i18n.UNLINKED]
        handled.assert_not_awaited()
        assert "42" not in user_renew._awaiting_code
    finally:
        user_renew._awaiting_code.discard("42")


def test_guest_cannot_open_more_menu(db, sent, monkeypatch):
    more = AsyncMock()
    monkeypatch.setattr(menu, "handle_more_menu", more)

    _run_text(db, i18n.BTN_MENU_MORE)

    more.assert_not_awaited()
    assert _texts(sent) == [i18n.UNLINKED]


def test_guest_stale_more_callback_gets_unlinked_instead_of_menu(db, sent, monkeypatch):
    more = AsyncMock()
    monkeypatch.setattr(menu, "handle_more_menu", more)

    asyncio.run(menu.handle_menu_callback(_context(db), "nav:more", message_id=None))

    more.assert_not_awaited()
    assert _texts(sent) == [i18n.UNLINKED]


def test_guest_home_is_allowed(db, sent, monkeypatch):
    menu_text = AsyncMock(return_value=True)
    monkeypatch.setattr(bot_module, "handle_menu_text", menu_text)

    _run_text(db, i18n.BTN_MENU_HUB)

    menu_text.assert_awaited_once()
    assert sent == []


def test_guest_inline_home_callback_is_allowed(db, sent, monkeypatch):
    monkeypatch.setattr(bot_module, "answer_callback_query", AsyncMock())
    start = AsyncMock()
    monkeypatch.setattr("app.services.telegram_bot_handlers.start.handle_start", start)

    _run_callback(db, "nav:home")

    start.assert_awaited_once()
    assert i18n.UNLINKED not in _texts(sent)


def test_guest_inline_admin_callback_still_gets_unlinked(db, sent, monkeypatch):
    monkeypatch.setattr(bot_module, "answer_callback_query", AsyncMock())
    api_send = AsyncMock()
    monkeypatch.setattr("app.services.telegram_api.send_message", api_send)
    settings_callback = AsyncMock()
    monkeypatch.setattr(bot_module, "handle_settings_callback", settings_callback)

    _run_callback(db, "nav:settings")

    settings_callback.assert_not_awaited()
    api_send.assert_awaited_once()
    assert api_send.await_args.args[2] == i18n.UNLINKED


def test_guest_request_access_requires_enabled_requests(db, sent, monkeypatch):
    menu_text = AsyncMock(return_value=True)
    monkeypatch.setattr(bot_module, "handle_menu_text", menu_text)

    _run_text(db, i18n.BTN_REQUEST_ACCESS)
    assert _texts(sent) == [i18n.UNLINKED]
    menu_text.assert_not_awaited()

    _set_setting(db, "telegram_accept_access_requests", "true")
    db.commit()

    _run_text(db, i18n.BTN_REQUEST_ACCESS)
    menu_text.assert_awaited_once()


def test_public_command_over_the_limit_is_silently_ignored(db, sent, monkeypatch):
    start = AsyncMock()
    monkeypatch.setattr(bot_module, "handle_start", start)
    monkeypatch.setattr(
        bot_module.telegram_bot_command_rate_limit_service,
        "consume",
        lambda *_a, **_k: "Слишком много команд. Повторите через 60 с.",
    )

    asyncio.run(bot_module._dispatch_command(_context(db), "/start", ""))
    asyncio.run(bot_module._dispatch_command(_context(db), "/help", ""))

    assert sent == []
    start.assert_not_awaited()


def test_public_command_consumes_the_limiter_and_still_runs(db, sent, monkeypatch):
    start = AsyncMock()
    monkeypatch.setattr(bot_module, "handle_start", start)
    consumed: list[str] = []
    monkeypatch.setattr(
        bot_module.telegram_bot_command_rate_limit_service,
        "consume",
        lambda _db, telegram_user_id: consumed.append(telegram_user_id) or None,
    )

    asyncio.run(bot_module._dispatch_command(_context(db), "/start", ""))

    start.assert_awaited_once()
    assert consumed == ["42"]
