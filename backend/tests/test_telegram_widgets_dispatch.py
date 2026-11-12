"""Telegram-виджеты: авторизация widget_query и обновление карточки заявки."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.telegram_widgets import access_request as ar
from app.services.telegram_widgets import dispatch


class _FilteredQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def count(self):
        return 0

    def first(self):
        return self._row

    def all(self):
        return []


class _FakeDb:
    def __init__(self, *, row=None, request=None):
        self.row = row
        self.request = request
        self.commits = 0

    def query(self, model):
        return _FilteredQuery(self.row)

    def get(self, model, pk):
        return self.request

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _row(*, telegram_id: str = "42", last_state: str | None = None):
    return SimpleNamespace(
        chat_id="42",
        message_id=100,
        telegram_id=telegram_id,
        kind=ar.KIND_ACCESS_REQUEST,
        ref_id=7,
        last_state=last_state,
    )


def _request(status: str = "approved"):
    return SimpleNamespace(
        status=status,
        created_at=datetime(2026, 11, 12, 10, 0),
    )


def _query(
    *,
    chat_type: str = "private",
    from_id: int = 42,
    chat_id: int = 42,
    message_id: int = 100,
    data: str = "r",
):
    return {
        "id": "wq-1",
        "from": {"id": from_id},
        "chat": {"id": chat_id, "type": chat_type},
        "message_id": message_id,
        "data": data,
    }


def _wire(monkeypatch, *, edit_ok: bool = True):
    answered = AsyncMock(return_value=True)
    edited = AsyncMock(return_value=edit_ok)
    captioned = AsyncMock(return_value=True)
    monkeypatch.setattr(dispatch, "answer_widget_query", answered)
    monkeypatch.setattr(ar, "answer_widget_query", answered)
    monkeypatch.setattr(ar, "edit_widget_data", edited)
    monkeypatch.setattr(ar, "edit_message_caption", captioned)
    return answered, edited, captioned


def _run(db, query):
    asyncio.run(dispatch.handle_widget_query(db, query, bot_token="bot-token"))


def test_group_chat_is_answered_without_data(monkeypatch):
    answered, edited, _ = _wire(monkeypatch)
    db = _FakeDb(row=_row(), request=_request())

    _run(db, _query(chat_type="group", chat_id=-100))

    assert answered.await_args.kwargs.get("data") is None
    edited.assert_not_awaited()
    assert db.commits == 0


def test_foreign_sender_gets_no_data(monkeypatch):
    answered, edited, _ = _wire(monkeypatch)
    db = _FakeDb(row=_row(telegram_id="42"), request=_request())

    _run(db, _query(from_id=99, chat_id=42))

    # chat.id != from.id уже отсекает запрос до поиска строки.
    assert answered.await_args.kwargs.get("data") is None
    edited.assert_not_awaited()


def test_unknown_message_is_answered_empty(monkeypatch):
    answered, edited, _ = _wire(monkeypatch)
    db = _FakeDb(row=None, request=_request())

    _run(db, _query())

    assert answered.await_args.kwargs.get("data") is None
    edited.assert_not_awaited()


def test_unknown_action_answers_error_without_edit(monkeypatch):
    answered, edited, _ = _wire(monkeypatch)
    db = _FakeDb(row=_row(), request=_request())

    _run(db, _query(data="approve:7"))

    assert answered.await_args.kwargs["data"] == '{"e":"unknown"}'
    edited.assert_not_awaited()


def test_owner_refresh_updates_changed_status(monkeypatch):
    answered, edited, captioned = _wire(monkeypatch)
    request = _request(status="approved")
    db = _FakeDb(row=_row(last_state='{"s":"pending","t":"12.11.2026 10:00 UTC"}'), request=request)

    _run(db, _query())

    assert '"s":"approved"' in answered.await_args.kwargs["data"]
    edited.assert_awaited_once()
    captioned.assert_awaited_once()
    assert db.commits == 1


def test_owner_refresh_skips_unchanged_state(monkeypatch):
    answered, edited, _ = _wire(monkeypatch)
    request = _request(status="pending")
    db = _FakeDb(row=_row(last_state=ar._state_text(request)), request=request)

    _run(db, _query())

    assert '"s":"pending"' in answered.await_args.kwargs["data"]
    edited.assert_not_awaited()
    assert db.commits == 0


def test_bot_service_dispatches_widget_query(monkeypatch):
    from app.services import telegram_widgets as widgets
    from app.services.telegram_bot import TelegramBotService
    from app.services.telegram_bot_handlers.base import TelegramBotSettingsSnapshot

    snap = TelegramBotSettingsSnapshot(
        bot_token="bot-token",
        interactive_enabled=True,
        bot_username="bot",
        webhook_set_at="",
        webhook_secret_set=True,
        token_set=True,
    )
    monkeypatch.setattr(
        "app.services.telegram_bot.load_telegram_bot_settings_snapshot", lambda _db: snap
    )
    handler = AsyncMock()
    monkeypatch.setattr(widgets, "handle_widget_query", handler)

    asyncio.run(
        TelegramBotService().handle_update(
            MagicMock(), {"widget_query": _query()}, mini_app_url="https://p/api/tg-mini"
        )
    )

    handler.assert_awaited_once()
