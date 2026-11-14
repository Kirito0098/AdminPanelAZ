"""Меню бота при недоступных виджетах: Портал/чат/чек и inline-запасной ход."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserRole
from app.services import telegram_bot_i18n as i18n
from app.services import telegram_widgets
from app.services.telegram_bot_handlers import menu, start
from app.services.telegram_bot_handlers.base import BotContext, TelegramBotSettingsSnapshot
from app.services.user_access_requests import (
    SETTING_ACCEPT_REQUESTS,
    _set_setting,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    session = make()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _features(monkeypatch, *, enabled: set[str]) -> None:
    monkeypatch.setattr(
        menu, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda name: name in enabled)
    )


def _context(db, *, mini_app_url: str = "") -> BotContext:
    user = User(
        username="subscriber",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        telegram_id="4242",
    )
    db.add(user)
    db.commit()
    return BotContext(
        db=db,
        bot_token="token",
        chat_id=1,
        telegram_user_id=user.telegram_id,
        user=user,
        settings=TelegramBotSettingsSnapshot(
            bot_token="token",
            interactive_enabled=True,
            bot_username="bot",
            webhook_set_at="",
            webhook_secret_set=True,
            token_set=True,
        ),
        mini_app_url=mini_app_url,
    )


def _rows(keyboard: dict) -> list[list[str]]:
    return [[button["text"] for button in row] for row in keyboard["inline_keyboard"]]


def _callbacks(keyboard: dict) -> list[str]:
    return [
        button["callback_data"]
        for row in keyboard["inline_keyboard"]
        for button in row
        if "callback_data" in button
    ]


def test_portal_card_is_exported():
    assert callable(telegram_widgets.send_portal_card)
    assert "send_portal_card" in telegram_widgets.__all__


def test_subscriber_more_menu_lists_moved_actions(db, monkeypatch):
    _features(monkeypatch, enabled={"unlock_codes", "user_messaging"})
    _set_setting(db, SETTING_ACCEPT_REQUESTS, "true")

    keyboard = menu.build_more_inline_menu(_context(db))

    assert _callbacks(keyboard) == [
        "nav:redeem_unlock",
        "nav:request_more_config",
        "nav:portal",
        "nav:admin_chat",
        "nav:pay_request",
        "nav:help",
    ]
    labels = _rows(keyboard)
    assert [label for row in labels for label in row] == [
        i18n.BTN_REDEEM_UNLOCK,
        i18n.BTN_REQUEST_MORE_CONFIG,
        "Портал",
        "Написать администратору",
        "Оплатить (чек)",
        i18n.BTN_MENU_HELP,
    ]


def test_subscriber_more_menu_hides_actions_behind_toggles(db, monkeypatch):
    _features(monkeypatch, enabled=set())
    _set_setting(db, SETTING_ACCEPT_REQUESTS, "false")

    keyboard = menu.build_more_inline_menu(_context(db))

    assert _callbacks(keyboard) == ["nav:request_more_config", "nav:portal", "nav:help"]


def test_start_fallback_menu_adds_mini_app_button(db, monkeypatch):
    _features(monkeypatch, enabled={"unlock_codes", "user_messaging"})
    sent: list[dict] = []

    async def fake_send(_token, _chat_id, text, **kwargs):
        sent.append({"text": text, "markup": kwargs.get("reply_markup")})

    async def no_hub(*_args, **_kwargs) -> bool:
        return False

    monkeypatch.setattr(start, "send_message", fake_send)
    monkeypatch.setattr(telegram_widgets, "send_hub", no_hub)

    asyncio.run(start.handle_start(_context(db, mini_app_url="https://panel.test/api/tg-mini")))

    fallback = sent[-1]["markup"]
    assert fallback["inline_keyboard"][-1] == [
        {"text": "Открыть Mini App", "web_app": {"url": "https://panel.test/api/tg-mini"}}
    ]
    assert "nav:portal" in _callbacks(fallback)
