"""Stage 2 Task 13: Telegram privacy §6.9 regressions для поверхностей заявок.

Покрытие:
- инлайн в группе — только статья «только в личном чате», без документов/ссылок;
- уведомление админам о новой заявке не использует telegram_chat_id (только telegram_id админов);
- бот покидает группу по my_chat_member (не регрессия Stage 0);
- колбэк заявки ignorуется, когда chat.id != from.id.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, User, UserRole, UserAccessRequest
from app.services.telegram_bot import TelegramBotService
from app.services.telegram_bot_handlers.base import TelegramBotSettingsSnapshot
from app.services.telegram_bot_handlers.inline import build_inline_results
from app.services.user_access_requests import _notify_admins_new_request

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
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _admin_user() -> User:
    return User(id=1, username="admin", password_hash="x", role=UserRole.admin, telegram_id="42")


def _req(db, telegram_id="111") -> UserAccessRequest:
    req = UserAccessRequest(
        request_type="new_user",
        telegram_id=telegram_id,
        telegram_name="ivan",
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def test_inline_group_has_no_document_or_url():
    ctx = SimpleNamespace(
        db=MagicMock(),
        user=_admin_user(),
        telegram_user_id=42,
        bot_token="token",
        mini_app_url="https://example.com/api/tg-mini",
    )
    results = build_inline_results(ctx, "ivan", chat_type="supergroup")
    assert len(results) == 1
    assert results[0]["id"] == "private_only"
    assert results[0]["type"] == "article"
    assert "document" not in results[0]
    blob = str(results)
    assert "http" not in blob.lower() or "mini_app" in blob


def test_request_notify_never_uses_telegram_chat_id(db, monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(
        "app.services.telegram_recipients.get_setting_chat_ids",
        lambda *a, **k: called.append("chat_ids") or ["-100123"],
    )
    admin = _admin_user()
    db.add(admin)
    db.commit()

    sent: list[dict] = []

    async def fake_send_photo(token, chat_id, file_id, **_kwargs):
        sent.append({"chat_id": chat_id, "file_id": file_id})
        return {"message_id": 1}

    async def fake_call_bot_api(token, method, payload=None):
        sent.append({"method": method, "chat_id": payload.get("chat_id") if payload else None})
        return {"message_id": 1}

    monkeypatch.setattr(
        "app.services.user_access_requests.telegram_api.send_photo", fake_send_photo
    )
    monkeypatch.setattr(
        "app.services.user_access_requests.telegram_api.call_bot_api", fake_call_bot_api
    )
    monkeypatch.setattr(
        "app.services.user_access_requests.get_feature_service",
        lambda: MagicMock(is_enabled=lambda _k: True),
    )

    _notify_admins_new_request(db, _req(db, "111"))

    assert called == [], "get_setting_chat_ids не должен вызываться для карточек заявок"
    for item in sent:
        assert item.get("chat_id") != "-100123"


def test_bot_leaves_group_on_my_chat_member(monkeypatch):
    left = []

    async def fake_leave_chat(*_a, **_k):
        left.append(True)
        return True

    monkeypatch.setattr("app.services.telegram_bot.leave_chat", fake_leave_chat)
    service = TelegramBotService()
    asyncio.run(
        service._handle_my_chat_member(
            "TOKEN",
            {
                "chat": {"id": -100, "type": "supergroup"},
                "new_chat_member": {"status": "member"},
            },
        )
    )
    assert left == [True]


def test_request_callback_rejected_when_chat_id_ne_from_id(monkeypatch):
    """Callback-заявка из чужого чата (chat.id != from.id) не обрабатывается."""
    answer = AsyncMock()
    monkeypatch.setattr("app.services.telegram_bot.answer_callback_query", answer)
    dispatch_callback = MagicMock()
    monkeypatch.setattr("app.services.telegram_bot._dispatch_callback", dispatch_callback)
    monkeypatch.setattr(
        "app.services.telegram_bot.load_telegram_bot_settings_snapshot", lambda _db: _SNAP
    )

    service = TelegramBotService()
    asyncio.run(
        service.handle_update(
            MagicMock(),
            {
                "callback_query": {
                    "id": "cb",
                    "data": "ar:a:1",
                    "from": {"id": 42},
                    "message": {"message_id": 1, "chat": {"id": -100, "type": "supergroup"}},
                }
            },
            mini_app_url="https://p/api/tg-mini",
        )
    )
    dispatch_callback.assert_not_called()
