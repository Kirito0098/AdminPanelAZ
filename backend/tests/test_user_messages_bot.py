"""Бот: режим переписки с админом (текст уходит в чат, дубли не пишутся)."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserMessage, UserRole
from app.services.telegram_bot_handlers import chat as chat_handler
from app.services import telegram_bot_i18n as i18n


class _Feature:
    def is_enabled(self, key: str) -> bool:
        return True


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def subscriber(db):
    user = User(
        username="ivan", password_hash="x", role=UserRole.user, is_active=True,
        panel_login_enabled=True, telegram_id="555", client_base_name="ivan",
        plan_config_indexes="[1]",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _ctx(db, user) -> SimpleNamespace:
    return SimpleNamespace(
        db=db, user=user, bot_token="tok", chat_id=555, telegram_user_id="555",
        telegram_username="ivan", telegram_name="Ivan", mini_app_url="https://panel.test",
    )


def _message(text: str, message_id: int = 10) -> dict:
    return {
        "message_id": message_id,
        "text": text,
        "chat": {"id": 555, "type": "private"},
        "from": {"id": 555},
    }


@pytest.fixture(autouse=True)
def _silent_telegram(monkeypatch):
    monkeypatch.setattr(chat_handler, "get_feature_service", lambda: _Feature())
    # send_message в хендлерах асинхронный — подменяем AsyncMock, иначе await падает.
    monkeypatch.setattr(chat_handler, "send_message", AsyncMock())


def test_admin_button_enters_chat_mode(db, subscriber):
    import asyncio

    asyncio.run(chat_handler.handle_admin_chat(_ctx(db, subscriber)))

    db.refresh(subscriber)
    assert subscriber.chat_mode_since is not None


def test_chat_text_saved_when_mode_on(db, subscriber):
    import asyncio

    subscriber.chat_mode_since = datetime.utcnow()
    db.commit()

    handled = asyncio.run(
        chat_handler.handle_chat_text(_ctx(db, subscriber), _message("Почему не работает VPN?"))
    )

    assert handled is True
    rows = db.query(UserMessage).all()
    assert len(rows) == 1
    assert rows[0].direction == "in"
    assert rows[0].text == "Почему не работает VPN?"
    assert rows[0].telegram_message_id == 10


def test_duplicate_update_does_not_duplicate(db, subscriber):
    import asyncio

    subscriber.chat_mode_since = datetime.utcnow()
    db.commit()

    asyncio.run(chat_handler.handle_chat_text(_ctx(db, subscriber), _message("дубль", 11)))
    asyncio.run(chat_handler.handle_chat_text(_ctx(db, subscriber), _message("дубль", 11)))

    assert db.query(UserMessage).count() == 1


def test_text_ignored_when_mode_off(db, subscriber):
    import asyncio

    assert asyncio.run(
        chat_handler.handle_chat_text(_ctx(db, subscriber), _message("привет"))
    ) is False
    assert db.query(UserMessage).count() == 0


def test_stop_leaves_chat_mode(db, subscriber):
    import asyncio

    subscriber.chat_mode_since = datetime.utcnow()
    db.commit()

    asyncio.run(chat_handler.handle_chat_stop(_ctx(db, subscriber)))

    db.refresh(subscriber)
    assert subscriber.chat_mode_since is None


def test_chat_disabled_without_module(db, subscriber):
    import asyncio

    with patch.object(
        chat_handler,
        "get_feature_service",
        lambda: SimpleNamespace(is_enabled=lambda key: False),
    ):
        asyncio.run(chat_handler.handle_admin_chat(_ctx(db, subscriber)))

    db.refresh(subscriber)
    assert subscriber.chat_mode_since is None


def test_start_payload_chat_enters_mode(db, subscriber):
    import asyncio

    from app.services.telegram_bot_handlers.start import handle_start

    asyncio.run(handle_start(_ctx(db, subscriber), payload="chat"))

    db.refresh(subscriber)
    assert subscriber.chat_mode_since is not None


def test_pay_button_creates_extend_request(db, subscriber, monkeypatch):
    import asyncio

    from app.services.telegram_bot_handlers import access_requests as ar

    calls = []
    monkeypatch.setattr(
        ar, "submit_access_request", lambda db, **kwargs: calls.append(kwargs)
    )
    monkeypatch.setattr(ar, "send_message", AsyncMock())

    asyncio.run(ar.handle_pay_request(_ctx(db, subscriber)))

    assert calls and calls[0]["request_type"] == "extend_access"
    assert calls[0]["user_id"] == subscriber.id
    assert calls[0]["requested_count"] == 1


def test_start_payload_pay_creates_request(db, subscriber, monkeypatch):
    import asyncio

    from app.services.telegram_bot_handlers import access_requests as ar
    from app.services.telegram_bot_handlers.start import handle_start

    calls = []
    monkeypatch.setattr(
        ar, "submit_access_request", lambda db, **kwargs: calls.append(kwargs)
    )
    monkeypatch.setattr(ar, "send_message", AsyncMock())

    asyncio.run(handle_start(_ctx(db, subscriber), payload="pay"))

    assert calls and calls[0]["request_type"] == "extend_access"


def test_new_message_writes_bell_and_one_card(db, subscriber, monkeypatch):
    import asyncio

    from app.models import AdminPanelNotification
    from app.services import user_message_notify as notify_mod

    cards: list[str] = []

    async def _fake_call(token, method, *, payload=None):
        cards.append(payload["chat_id"])
        return {"message_id": 900 + len(cards)}

    monkeypatch.setattr(notify_mod.telegram_api, "call_bot_api", _fake_call)
    monkeypatch.setattr(notify_mod, "_get_setting", lambda db, key, default=None: "bot-token")
    admin = User(
        username="admin", password_hash="x", role=UserRole.admin, is_active=True,
        panel_login_enabled=True, telegram_id="777",
    )
    db.add(admin)
    db.commit()

    subscriber.chat_mode_since = datetime.utcnow()
    db.commit()

    asyncio.run(chat_handler.handle_chat_text(_ctx(db, subscriber), _message("раз", 21)))
    asyncio.run(chat_handler.handle_chat_text(_ctx(db, subscriber), _message("два", 22)))

    # Карточка в Telegram — только на первое непрочитанное сообщение диалога.
    assert cards == ["777"]
    bells = db.query(AdminPanelNotification).filter_by(event_type="user_message").all()
    assert len(bells) == 2
    assert bells[0].title.startswith("ivan:")

    from app.models import UserMessageCard

    saved_cards = db.query(UserMessageCard).all()
    assert len(saved_cards) == 1
    assert saved_cards[0].admin_chat_id == "777"
    assert saved_cards[0].user_id == subscriber.id


def _admin_ctx(db, admin) -> SimpleNamespace:
    return SimpleNamespace(
        db=db, user=admin, bot_token="tok", chat_id=777, telegram_user_id="777",
        telegram_username="boss", telegram_name="Boss", mini_app_url="https://panel.test",
    )


def _admin(db, telegram_id="777") -> User:
    user = User(
        username="boss", password_hash="x", role=UserRole.admin, is_active=True,
        panel_login_enabled=True, telegram_id=telegram_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_admin_card_reply_reaches_subscriber(db, subscriber, monkeypatch):
    import asyncio

    from app.models import UserMessageCard
    from app.services import user_messages as chat_service

    admin = _admin(db)
    chat_service.record_card(db, admin_chat_id="777", message_id=900, user_id=subscriber.id)
    monkeypatch.setattr(chat_service, "_get_setting", lambda db, key, default=None: "bot-token")
    monkeypatch.setattr(chat_service, "send_tg_message_result", lambda *a, **k: (True, None))
    message = {
        "message_id": 1000,
        "text": "Здравствуйте",
        "reply_to_message": {"message_id": 900},
        "chat": {"id": 777, "type": "private"},
        "from": {"id": 777},
    }

    handled = asyncio.run(chat_handler.handle_admin_card_reply(_admin_ctx(db, admin), message))

    assert handled is True
    saved = db.query(UserMessage).filter_by(direction="out").one()
    assert saved.admin_id == admin.id
    assert saved.text == "Здравствуйте"
    assert db.query(UserMessageCard).count() == 1


def test_admin_card_reply_ignores_unknown_card(db, subscriber):
    import asyncio

    admin = _admin(db)
    message = {
        "message_id": 1001,
        "text": "Ответ",
        "reply_to_message": {"message_id": 555},
        "chat": {"id": 777, "type": "private"},
        "from": {"id": 777},
    }

    assert asyncio.run(
        chat_handler.handle_admin_card_reply(_admin_ctx(db, admin), message)
    ) is False
    assert db.query(UserMessage).count() == 0


def test_subscriber_cannot_reply_to_card(db, subscriber):
    import asyncio

    message = {
        "message_id": 1002,
        "text": "Ответ",
        "reply_to_message": {"message_id": 900},
        "chat": {"id": 555, "type": "private"},
        "from": {"id": 555},
    }

    assert asyncio.run(
        chat_handler.handle_admin_card_reply(_ctx(db, subscriber), message)
    ) is False


def test_user_message_notification_goes_to_requests_tab():
    from app.services.admin_panel_notifications import category_for_event

    assert category_for_event("user_message") == "requests"


def test_admin_does_not_enter_chat_mode(db):
    import asyncio

    admin = User(
        username="boss", password_hash="x", role=UserRole.admin, is_active=True,
        panel_login_enabled=True, telegram_id="999",
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    asyncio.run(chat_handler.handle_admin_chat(_ctx(db, admin)))

    db.refresh(admin)
    assert admin.chat_mode_since is None
    assert chat_handler.send_message.await_args.args[2] == i18n.CHAT_ADMIN_HINT


def test_photo_in_chat_mode_hints_text_only(db, subscriber):
    import asyncio

    subscriber.chat_mode_since = datetime.utcnow()
    db.commit()
    photo_message = {
        "message_id": 31,
        "photo": [{"file_id": "f"}],
        "chat": {"id": 555, "type": "private"},
        "from": {"id": 555},
    }

    handled = asyncio.run(chat_handler.handle_chat_text(_ctx(db, subscriber), photo_message))

    assert handled is True
    assert db.query(UserMessage).count() == 0
    assert chat_handler.send_message.await_args.args[2] == i18n.CHAT_TEXT_ONLY
