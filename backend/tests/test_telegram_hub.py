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
    assert "Заявки" in labels
    assert state["m"][2][3] == 3
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


def test_guest_cannot_open_role_views(monkeypatch):
    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: None)
    answered, edited = _wire(monkeypatch)

    asyncio.run(hub.handle_query(_FakeDb(), _row(), _query("v:nodes"), bot_token="t"))
    asyncio.run(hub.handle_query(_FakeDb(), _row(), _query("v:configs"), bot_token="t"))

    assert answered.await_args.kwargs["data"] == '{"e":"forbidden"}'
    edited.assert_not_awaited()


def test_user_cannot_open_admin_nodes_view(monkeypatch):
    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: _plain_user())
    answered, edited = _wire(monkeypatch)

    asyncio.run(hub.handle_query(_FakeDb(), _row(), _query("v:nodes"), bot_token="t"))

    assert answered.await_args.kwargs["data"] == '{"e":"forbidden"}'
    edited.assert_not_awaited()


def test_user_can_open_configs_view(monkeypatch):
    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: _plain_user())
    answered, edited = _wire(monkeypatch)

    asyncio.run(hub.handle_query(_FakeDb(), _row(), _query("v:configs"), bot_token="t"))

    assert answered.await_args.kwargs["data"] == '{"ok":1}'
    edited.assert_awaited_once()


def test_configs_view_lists_config_with_traffic(monkeypatch):
    from datetime import datetime

    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: _plain_user())
    config = SimpleNamespace(
        id=12,
        client_name="ivan-phone",
        vpn_type=SimpleNamespace(value="wireguard"),
        node_id=1,
        expires_at=datetime(2026, 12, 31),
        cert_expires_at=None,
    )
    monkeypatch.setattr(
        "app.services.telegram_bot_data.list_user_configs", lambda db, user: [config]
    )
    monkeypatch.setattr(
        "app.services.telegram_bot_data.node_labels", lambda db, ids: {1: "nl-1"}
    )
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.traffic.traffic_by_client",
        lambda db, user: {"ivan-phone": 1024},
    )

    state = hub.build_state(_FakeDb(), telegram_id="42", view="configs")

    item = state["cf"]["c"][0]
    assert item["n"] == "ivan-phone"
    assert item["p"] == "WG/AWG 1.5"
    assert item["nd"] == "nl-1"
    assert item["d"] == "31.12.26"
    assert item["t"]


def test_awg2_module_label_is_unified(monkeypatch):
    monkeypatch.setattr(hub, "_feature_on", lambda key: True)

    more_items = [item[1] for item in hub._more_items(_FakeDb())]
    help_items = [item[1] for item in hub._help_items(_FakeDb(), "admin")]

    assert "AWG 2.0" in more_items
    assert any(label.startswith("/awg2") and "AWG 2.0" in label for label in help_items)


def test_nodes_view_marks_active_node(monkeypatch):
    from app.models import NodeStatus

    monkeypatch.setattr(hub, "resolve_user", lambda db, tid: _admin_user())
    monkeypatch.setattr(hub, "_pending_count", lambda db: 0)
    nodes = [
        SimpleNamespace(id=1, name="nl-1", status=NodeStatus.online),
        SimpleNamespace(id=2, name="msk-1", status=NodeStatus.offline),
    ]
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.nodes._list_nodes", lambda db: nodes
    )
    monkeypatch.setattr("app.services.node_manager.get_active_node_id", lambda db: 1)

    state = hub.build_state(_FakeDb(), telegram_id="42", view="nodes")

    assert state["nl"]["c"][0] == {"i": 1, "n": "nl-1", "s": "on", "a": 1}
    assert state["nl"]["c"][1]["s"] == "off"
    assert state["nl"]["c"][1]["a"] == 0


# Всё, что виджет может показать сам. Новый пункт меню обязан быть видом (v:),
# обновлением (r) или осознанно добавленным исключением из списка ниже.
_MESSAGE_ACTIONS = {
    "a:configs",  # полный список с фильтрами/пагинацией
    "a:nodes",  # полный список узлов
    "a:settings",  # формы настроек
    "a:unlock",  # FSM: срок и протоколы вводятся текстом
    "a:redeem_unlock",  # FSM активации ключа
    "a:pay_request",  # заявка + фото чека
    "a:admin_chat",  # режим переписки
    "a:request_more_config",  # действие-заявка, не экран
    "a:request_access",  # отправляет карточку-виджет заявки
    "a:portal",  # отдельная карточка-виджет ссылки портала
}


def _all_items(monkeypatch, role: str) -> list[list[str]]:
    monkeypatch.setattr(hub, "_feature_on", lambda key: True)
    monkeypatch.setattr(hub, "_accept_requests", lambda db: True)
    user = _admin_user() if role == "admin" else _plain_user() if role == "user" else None
    items = hub._menu_items(_FakeDb(), user, role, 0)
    if role == "admin":
        items = items + hub._more_items(_FakeDb())
    items = items + hub._help_items(_FakeDb(), role)
    return items


def test_every_widget_target_is_a_view_or_known_message_action(monkeypatch):
    for role in ("admin", "user", "guest"):
        for item in _all_items(monkeypatch, role):
            target = item[2]
            assert target.startswith("v:") or target in ("r", "a:home") or target in _MESSAGE_ACTIONS, (
                role,
                item,
            )
