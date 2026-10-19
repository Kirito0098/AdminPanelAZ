"""Stage 2 Task 10: бот — заявки на доступ и админские callback (6.9).

Только личный чат (chat.id == from.id). Карточки заявок — только в личные чаты
админов (их telegram_id). Callback data — только id заявки, без ссылок.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    Base,
    Node,
    NodeStatus,
    ProvisioningPreset,
    User,
    UserAccessRequest,
    UserRole,
)
from app.services.provisioning_presets import create_preset
from app.services.app_setting_store import _set_setting
from app.services.telegram_bot import TelegramBotService
from app.services.telegram_bot_handlers.access_requests import RateLimitExceeded
from app.services.telegram_bot_handlers.base import TelegramBotSettingsSnapshot
from app.services.user_access_requests import (
    approve_request,
    reject_request,
    submit_access_request,
    sync_admin_request_messages,
)

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


@pytest.fixture()
def admin(db):
    user = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True, telegram_id="100")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def subscriber(db):
    user = User(username="sub", password_hash="x", role=UserRole.user, is_active=True, telegram_id="200")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def node(db):
    node = Node(
        name="n1",
        host="127.0.0.1",
        port=9100,
        api_key_hash="h",
        api_key_encrypted="e",
        status=NodeStatus.online,
        is_local=True,
        node_kind="vpn",
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@pytest.fixture()
def default_preset(db, node):
    return create_preset(
        db,
        name="trial-3d",
        node_ids=[node.id],
        protocols=["wireguard"],
        config_count=1,
        access_days=3,
        is_default=True,
    )


@pytest.fixture()
def pending_new_user(db, subscriber):
    req = UserAccessRequest(
        request_type="new_user",
        telegram_id="200",
        telegram_name="Ivan",
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@pytest.fixture()
def pending_extend(db, subscriber):
    req = UserAccessRequest(
        request_type="extend_access",
        user_id=subscriber.id,
        telegram_id="200",
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def fake_approve(db, request_id, admin, **_kw):
    req = db.get(UserAccessRequest, request_id)
    req.status = "approved"
    req.reviewed_by_id = admin.id
    req.reviewed_at = datetime.utcnow()
    db.commit()
    return req


def fake_reject(db, request_id, admin, **_kw):
    req = db.get(UserAccessRequest, request_id)
    req.status = "rejected"
    req.reviewed_by_id = admin.id
    req.reviewed_at = datetime.utcnow()
    db.commit()
    return req


@pytest.fixture
def env(db, admin, subscriber, monkeypatch):
    monkeypatch.setattr(
        "app.services.telegram_bot.load_telegram_bot_settings_snapshot", lambda _db: _SNAP
    )

    def resolve(_db, tg_id):
        tg_id = str(tg_id)
        if tg_id == admin.telegram_id:
            return admin
        if tg_id == subscriber.telegram_id:
            return subscriber
        return None

    monkeypatch.setattr("app.services.telegram_bot.resolve_user", resolve)

    answer = AsyncMock()
    monkeypatch.setattr("app.services.telegram_bot.answer_callback_query", answer)
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.answer_callback_query", answer
    )
    send_message = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.send_message", send_message
    )
    monkeypatch.setattr("app.services.telegram_bot_handlers.menu.send_message", send_message)
    monkeypatch.setattr("app.services.telegram_bot_handlers.start.send_message", send_message)
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.edit_message_reply_markup",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.approve_request", fake_approve
    )
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.reject_request", fake_reject
    )
    sync_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.sync_admin_request_messages", sync_mock
    )
    return SimpleNamespace(
        db=db,
        answer=answer,
        send_message=send_message,
        sync=sync_mock,
    )


def _run(env, update):
    asyncio.run(TelegramBotService().handle_update(env.db, update, mini_app_url="https://p/api/tg-mini"))


def _callback(data, from_id, chat_id, message_id=5, callback_id="cb"):
    return {
        "callback_query": {
            "id": callback_id,
            "data": data,
            "from": {"id": from_id},
            "message": {"message_id": message_id, "chat": {"id": chat_id, "type": "private"}},
        }
    }


def _message(text, from_id, chat_id, photo=None, document=None):
    message = {"text": text, "from": {"id": from_id}, "chat": {"id": chat_id, "type": "private"}}
    if photo is not None:
        message["photo"] = photo
    if document is not None:
        message["document"] = document
    return {"message": message}


def test_admin_callback_rejected_for_non_admin(env, pending_new_user, monkeypatch):
    # Подписчик (не админ) нажимает ar:a — «Недостаточно прав», заявка остаётся pending.
    _run(env, _callback(f"ar:a:{pending_new_user.id}", "200", "200"))
    answer_texts = [c.kwargs.get("text") or "" for c in env.answer.await_args_list]
    assert any("Недостаточно прав" in t for t in answer_texts)
    assert any(c.kwargs.get("show_alert") is True for c in env.answer.await_args_list)
    row = env.db.get(UserAccessRequest, pending_new_user.id)
    assert row.status == "pending"


def test_message_ignored_when_chat_id_ne_from_id(env, monkeypatch):
    # chat.id != from.id — ничего не шлется и заявка не создаётся.
    calls = []
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.submit_access_request",
        lambda *a, **k: calls.append((a, k)),
    )
    _run(env, _message("Запросить доступ", 300, 400))
    assert calls == []
    env.send_message.assert_not_awaited()


def test_request_access_from_unbound_creates_request(env, monkeypatch, db):
    # Новый пользователь (не привязан) может подать на new_user, если приём включён.
    _set_setting(db, "telegram_accept_access_requests", "true")
    db.commit()
    _run(env, _message("Запросить доступ", "300", "300"))
    env.send_message.assert_awaited()
    sent_text = env.send_message.await_args.args[2]
    assert "Заявка отправлена администратору" in sent_text
    row = (
        env.db.query(UserAccessRequest)
        .filter(UserAccessRequest.telegram_id == "300", UserAccessRequest.request_type == "new_user")
        .one()
    )
    assert row.status == "pending"


def test_request_access_closed_by_default(env, monkeypatch):
    # Приём выключен по умолчанию — нейтральный отказ, заявка не создаётся.
    _run(env, _message("Запросить доступ", "300", "300"))
    env.send_message.assert_awaited_with("bot-token", "300", "Приём заявок временно закрыт")
    assert env.db.query(UserAccessRequest).count() == 0


def test_link_code_hint(env):
    _run(env, _message("У меня есть код привязки", "300", "300"))
    env.send_message.assert_awaited()
    assert "/link" in env.send_message.await_args.args[2]


def test_start_unlinked_shows_request_access_when_accept_on(env, db):
    """Приём включён: /start для нового TG — кнопка «Запросить доступ» и подсказка в тексте."""
    _set_setting(db, "telegram_accept_access_requests", "true")
    db.commit()
    _run(env, _message("/start", "300", "300"))
    env.send_message.assert_awaited()
    args = env.send_message.await_args
    text = args.args[2]
    markup = args.kwargs.get("reply_markup") or {}
    buttons = [
        btn.get("text")
        for row in markup.get("keyboard", [])
        for btn in row
    ]
    assert "Запросить доступ" in buttons
    assert "Запросить доступ" in text
    assert "/link" in text


def test_start_unlinked_hides_request_access_when_accept_off(env, db):
    _set_setting(db, "telegram_accept_access_requests", "false")
    db.commit()
    _run(env, _message("/start", "300", "300"))
    env.send_message.assert_awaited()
    markup = env.send_message.await_args.kwargs.get("reply_markup") or {}
    buttons = [
        btn.get("text")
        for row in markup.get("keyboard", [])
        for btn in row
    ]
    assert "Запросить доступ" not in buttons
    assert "У меня есть код привязки" in buttons


def test_admin_approve_new_user_with_default_preset(env, pending_new_user, default_preset):
    _run(env, _callback(f"ar:a:{pending_new_user.id}", "100", "100"))
    row = env.db.get(UserAccessRequest, pending_new_user.id)
    assert row.status == "approved"
    env.sync.assert_awaited()
    assert env.sync.await_args.kwargs["text"] == "✅ Одобрено в веб-панели: admin"
    env.answer.assert_awaited()


def test_admin_reject_callback(env, pending_new_user):
    _run(env, _callback(f"ar:r:{pending_new_user.id}", "100", "100"))
    row = env.db.get(UserAccessRequest, pending_new_user.id)
    assert row.status == "rejected"
    env.sync.assert_awaited()
    assert env.sync.await_args.kwargs["text"] == "❌ Отклонено в веб-панели: admin"


def test_already_decided_second_admin_gets_rejected_text(env, pending_new_user, monkeypatch):
    # Заявка уже одобрена — «Заявка уже обработана», approve не вызывается.
    pending_new_user.status = "approved"
    env.db.commit()
    called = {"approve": False}

    def no_approve(db, request_id, admin, **kw):
        called["approve"] = True
        return None

    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.approve_request", no_approve
    )
    _run(env, _callback(f"ar:a:{pending_new_user.id}", "100", "100"))
    assert not called["approve"]
    env.answer.assert_awaited()
    assert env.answer.await_args.kwargs.get("text") == "Заявка уже обработана"


def test_extend_e30_and_e60(env, pending_extend):
    for action, days in (("e30", 30), ("e60", 60)):
        env.send_message.reset_mock()
        _run(env, _callback(f"ar:{action}:{pending_extend.id}", "100", "100"))
        row = env.db.get(UserAccessRequest, pending_extend.id)
        assert row.status == "approved"
        env.sync.assert_awaited()
        assert env.sync.await_args.kwargs["text"] == "✅ Одобрено в веб-панели: admin"
        # Откатываем статус, чтобы следующая итерация видела pending.
        row.status = "pending"
        env.db.commit()


def test_extend_custom_opens_panel(env, pending_extend, monkeypatch):
    called = {"approve": False}

    def no_approve(db, request_id, admin, **kw):
        called["approve"] = True
        return None

    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.approve_request", no_approve
    )
    _run(env, _callback(f"ar:ec:{pending_extend.id}", "100", "100"))
    row = env.db.get(UserAccessRequest, pending_extend.id)
    assert row.status == "pending"
    assert not called["approve"]
    sent = [call.args[2] for call in env.send_message.await_args_list]
    assert any("Задайте срок доступа" in text for text in sent)
    assert any(f"/users?request={pending_extend.id}" in text for text in sent)


def test_receipt_photo_attached(env, pending_extend, monkeypatch):
    calls = []

    def fake_attach(db, *, request_id, message, telegram_id):
        calls.append((request_id, message, telegram_id))

    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.attach_receipt_from_update", fake_attach
    )
    _run(
        env,
        _message(
            "",
            "200",
            "200",
            photo=[{"file_id": "s"}, {"file_id": "L", "width": 1280}],
        ),
    )
    assert calls == [(pending_extend.id, calls[0][1], "200")]
    assert calls[0][1]["photo"][-1]["file_id"] == "L"
    env.send_message.assert_awaited()
    assert "Чек принят" in str(env.send_message.await_args.args[2])


def test_receipt_document_replies_not_photo(env, pending_extend):
    _run(
        env,
        _message("", "200", "200", document={"mime_type": "image/jpeg", "file_id": "doc"}),
    )
    env.send_message.assert_awaited_with(
        "bot-token", "200", "Пришлите чек фотографией (не файлом)"
    )


def test_receipt_rate_limit(env, pending_extend, monkeypatch):
    monkeypatch.setattr(
        "app.services.telegram_bot_handlers.access_requests.attach_receipt_from_update",
        lambda *a, **k: (_ for _ in ()).throw(
            RateLimitExceeded(detail="Слишком много попыток прислать чек. Повторите позже.", window=600)
        ),
    )
    _run(
        env,
        _message("", "200", "200", photo=[{"file_id": "f"}]),
    )
    env.send_message.assert_awaited()
    assert "Слишком много попыток" in str(env.send_message.await_args.args[2])


def test_submit_already_pending(env, subscriber, db, pending_new_user):
    _set_setting(db, "telegram_accept_access_requests", "true")
    db.commit()
    _run(env, _message("Запросить доступ", "200", "200"))
    env.send_message.assert_awaited()
    assert "У вас уже есть заявка" in str(env.send_message.await_args.args[2])
