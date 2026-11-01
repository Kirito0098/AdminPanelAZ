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
