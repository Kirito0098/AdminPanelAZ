"""Hub-виджет: меню по ролям и защита админских действий."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.models import UserRole
from app.services.telegram_widgets import hub


class _FakeDb:
    def commit(self):
        pass

    def rollback(self):
        pass

    def get(self, model, pk):
        return None

    def query(self, model):
        return self


def _row():
    return SimpleNamespace(
        kind=hub.KIND_HUB,
        telegram_id="42",
        chat_id="42",
        message_id=100,
        last_state='{"v":"menu","r":"admin"}',
    )


def _query(data: str):
    return {
        "id": "wq-1",
        "from": {"id": 42, "username": "admin"},
        "chat": {"id": 42, "type": "private"},
        "message_id": 100,
        "data": data,
    }


def _wire(monkeypatch):
    answered = AsyncMock(return_value=True)
    edited = AsyncMock(return_value=True)
    monkeypatch.setattr(hub, "answer_widget_query", answered)
    monkeypatch.setattr(hub, "edit_widget_data", edited)
    monkeypatch.setattr(hub, "build_state", lambda db, **kwargs: {"v": kwargs.get("view", "menu")})
    return answered, edited


def _admin_user():
    return SimpleNamespace(role=UserRole.admin, username="admin", access_until=None)


def _plain_user():
    return SimpleNamespace(role=UserRole.user, username="ivan", access_until=None)


def test_admin_menu_lists_queue_and_modules(monkeypatch):
    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: _admin_user())
    monkeypatch.setattr(hub, "_pending_count", lambda db: 3)

    state = hub.build_state(_FakeDb(), telegram_id="42", view="menu")

    assert state["r"] == "admin"
    assert state["pc"] == 3
    labels = [item[1] for item in state["m"]]
    assert "Заявки (3)" in labels
    assert "Статус" in labels and "Конфиги" in labels


def test_guest_menu_hides_admin_actions(monkeypatch):
    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: None)
    monkeypatch.setattr(hub, "_accept_requests", lambda db: True)
    monkeypatch.setattr(hub, "_guest_status", lambda db, tid: "pending")

    state = hub.build_state(_FakeDb(), telegram_id="42", view="menu")

    assert state["r"] == "guest"
    actions = {item[2] for item in state["m"]}
    assert "a:request_access" in actions
    assert "a:settings" not in actions


def test_guest_cannot_run_admin_action(monkeypatch):
    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: None)
    monkeypatch.setattr(hub, "_accept_requests", lambda db: True)
    dispatch_action = AsyncMock()
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.menu._dispatch_action", dispatch_action
    )
    answered, _ = _wire(monkeypatch)

    asyncio.run(hub.handle_query(_FakeDb(), _row(), _query("a:settings"), bot_token="t"))

    dispatch_action.assert_not_awaited()
    assert answered.await_args.kwargs["data"] == '{"e":"forbidden"}'


def test_guest_cannot_decide_requests(monkeypatch):
    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: None)
    decided = MagicMock()
    monkeypatch.setattr(hub, "_decide", decided)
    answered, _ = _wire(monkeypatch)

    asyncio.run(hub.handle_query(_FakeDb(), _row(), _query("q:a:5"), bot_token="t"))

    decided.assert_not_called()
    assert answered.await_args.kwargs["data"] == '{"e":"forbidden"}'


def test_admin_approves_from_queue_and_refreshes_applicant_card(monkeypatch):
    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: _admin_user())
    monkeypatch.setattr(hub, "_decide", lambda *args, **kwargs: "ok")
    refreshed = AsyncMock()
    monkeypatch.setattr(hub, "refresh_access_request_cards", refreshed)
    answered, edited = _wire(monkeypatch)

    asyncio.run(hub.handle_query(_FakeDb(), _row(), _query("q:a:5"), bot_token="t"))

    assert answered.await_args.kwargs["data"] == '{"ok":1}'
    refreshed.assert_awaited_once_with(5)
    edited.assert_awaited_once()


def test_admin_reject_reports_already_decided(monkeypatch):
    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: _admin_user())
    monkeypatch.setattr(hub, "_decide", lambda *args, **kwargs: "decided")
    answered, edited = _wire(monkeypatch)

    asyncio.run(hub.handle_query(_FakeDb(), _row(), _query("q:r:5"), bot_token="t"))

    assert answered.await_args.kwargs["data"] == '{"e":"decided"}'
    edited.assert_not_awaited()


def test_view_switch_edits_state_without_new_message(monkeypatch):
    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: _plain_user())
    answered, edited = _wire(monkeypatch)

    asyncio.run(hub.handle_query(_FakeDb(), _row(), _query("v:traffic"), bot_token="t"))

    assert answered.await_args.kwargs["data"] == '{"ok":1}'
    edited.assert_awaited_once()
    assert "traffic" in edited.await_args.kwargs["chat_data"]
