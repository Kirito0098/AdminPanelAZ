"""Stage 2 Task 10: бот — заявки на доступ и админские callback (6.9).

Только личный чат (chat.id == from.id). Карточки заявок — только в личные чаты
админов (их telegram_id). Callback data — только id заявки, без ссылок.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    AdminPanelNotification,
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
    _admin_request_keyboard,
    _notify_admins_new_request,
    approve_request,
    backfill_request_profile,
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


def _message(
    text,
    from_id,
    chat_id,
    photo=None,
    document=None,
    username=None,
    first_name=None,
    last_name=None,
):
    from_user = {"id": from_id}
    if username is not None:
        from_user["username"] = username
    if first_name is not None:
        from_user["first_name"] = first_name
    if last_name is not None:
        from_user["last_name"] = last_name
    message = {"text": text, "from": from_user, "chat": {"id": chat_id, "type": "private"}}
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


def test_submit_already_pending(env, db):
    _set_setting(db, "telegram_accept_access_requests", "true")
    db.add(
        UserAccessRequest(request_type="new_user", telegram_id="300", status="pending")
    )
    db.commit()
    _run(env, _message("Запросить доступ", "300", "300"))
    env.send_message.assert_awaited()
    assert "У вас уже есть заявка" in str(env.send_message.await_args.args[2])


def test_request_access_from_bound_user_returns_menu_and_no_duplicate(env, subscriber, db):
    """Старая кнопка «Запросить доступ» после одобрения: заявки нет, вернулось меню абонента."""
    _set_setting(db, "telegram_accept_access_requests", "true")
    db.commit()
    _run(env, _message("Запросить доступ", "200", "200"))
    env.send_message.assert_awaited()
    sent = env.send_message.await_args
    assert "У вас уже есть доступ" in str(sent.args[2])
    markup = sent.kwargs.get("reply_markup") or {}
    buttons = [btn.get("text") for row in markup.get("keyboard", []) for btn in row]
    assert "Запросить доступ" not in buttons
    assert "Запросить ещё конфиг" in buttons
    assert (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.telegram_id == subscriber.telegram_id)
        .count()
        == 0
    )


def test_request_access_stores_telegram_name_and_username(env, db):
    """Имя и @ник из update попадают в заявку и в ленту уведомлений."""
    _set_setting(db, "telegram_accept_access_requests", "true")
    db.commit()
    _run(
        env,
        _message(
            "Запросить доступ",
            "300",
            "300",
            username="ivan_petrov",
            first_name="Иван",
            last_name="Петров",
        ),
    )
    row = (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.telegram_id == "300")
        .one()
    )
    assert row.telegram_username == "ivan_petrov"
    assert row.telegram_name == "Иван Петров"

    notification = (
        db.query(AdminPanelNotification)
        .filter(AdminPanelNotification.event_type == "access_request_new_user")
        .one()
    )
    assert "новый пользователь" in notification.title
    assert "Иван Петров" in notification.message
    assert "@ivan_petrov" in notification.message


def test_new_user_keyboard_offers_configure_without_default_preset(db, pending_new_user):
    """Без шаблона по умолчанию админ видит «Настроить», а не только «Отклонить»."""
    keyboard = _admin_request_keyboard(db, pending_new_user)
    assert keyboard is not None
    buttons = [button["text"] for row in keyboard["inline_keyboard"] for button in row]
    assert buttons == ["Настроить", "Отклонить"]


def test_new_user_keyboard_offers_approve_with_default_preset(db, pending_new_user, default_preset):
    keyboard = _admin_request_keyboard(db, pending_new_user)
    assert keyboard is not None
    buttons = [button["text"] for row in keyboard["inline_keyboard"] for button in row]
    assert buttons == ["Одобрить", "Отклонить"]


def test_admin_card_shows_name_username_and_human_type(env, db, admin, monkeypatch):
    """Карточка админу: человеческий тип заявки, имя, @ник и Telegram ID."""
    req = UserAccessRequest(
        request_type="new_user",
        telegram_id="777",
        telegram_username="ivan_p",
        telegram_name="Иван Петров",
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    sent: dict[str, str] = {}

    async def fake_call_bot_api(_token, _method, payload=None):
        sent["text"] = (payload or {}).get("text", "")
        return {"message_id": 10}

    monkeypatch.setattr(
        "app.services.user_access_requests.telegram_api.call_bot_api", fake_call_bot_api
    )
    monkeypatch.setattr(
        "app.services.user_access_requests.get_feature_service",
        lambda: SimpleNamespace(is_enabled=lambda _key: True),
    )
    monkeypatch.setattr(
        "app.services.user_access_requests._bot_token", lambda _db: "bot-token"
    )

    _notify_admins_new_request(db, req)

    assert "новый пользователь" in sent["text"]
    assert "Имя: Иван Петров" in sent["text"]
    assert "Ник: @ivan_p" in sent["text"]
    assert "Telegram ID: <code>777</code>" in sent["text"]
    assert "new_user" not in sent["text"].splitlines()[0]


def test_no_preset_approve_click_sends_panel_link(env, db, admin, pending_new_user):
    """«Настроить» без шаблона: бот отправляет ссылку на заявку в панели."""
    _run(env, _callback(f"ar:a:{pending_new_user.id}", "100", "100"))
    assert env.send_message.await_args.kwargs.get("reply_markup") == {
        "inline_keyboard": [
            [
                {
                    "text": "Открыть заявку в панели",
                    "url": f"https://p/users?request={pending_new_user.id}",
                }
            ]
        ]
    }
    assert "Шаблон по умолчанию не задан" in env.send_message.await_args.args[2]
    row = env.db.get(UserAccessRequest, pending_new_user.id)
    assert row.status == "pending"


def test_backfill_request_profile_from_getchat(env, db, pending_new_user, monkeypatch):
    """Старая заявка без имени дозаполняется через getChat, карточка обновляется."""
    pending_new_user.telegram_name = None
    pending_new_user.telegram_username = None
    pending_new_user.admin_message_refs = json.dumps([{"chat_id": "100", "message_id": 5}])
    db.commit()

    calls: list[str] = []

    async def fake_call_bot_api(_token, method, payload=None):
        calls.append(method)
        if method == "getChat":
            return {
                "id": 200,
                "first_name": "Иван",
                "last_name": "Петров",
                "username": "ivan_p",
            }
        return {"message_id": 5}

    monkeypatch.setattr(
        "app.services.user_access_requests.telegram_api.call_bot_api", fake_call_bot_api
    )
    monkeypatch.setattr(
        "app.services.user_access_requests._bot_token", lambda _db: "bot-token"
    )
    monkeypatch.setattr(
        "app.services.user_access_requests.get_feature_service",
        lambda: SimpleNamespace(is_enabled=lambda _key: True),
    )
    monkeypatch.setattr("app.services.user_access_requests._profile_backfill_attempted", {})
    edit = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.user_access_requests.edit_message_text", edit)

    assert backfill_request_profile(db, pending_new_user) is True
    db.refresh(pending_new_user)
    assert pending_new_user.telegram_name == "Иван Петров"
    assert pending_new_user.telegram_username == "ivan_p"
    assert "getChat" in calls
    edit.assert_awaited()
    assert "Имя: Иван Петров" in edit.await_args.args[3]
    assert "Ник: @ivan_p" in edit.await_args.args[3]


def test_backfill_skips_requests_with_profile(db, pending_new_user, monkeypatch):
    pending_new_user.telegram_name = "Уже есть"
    db.commit()
    calls: list[str] = []

    async def fake_call_bot_api(_token, method, _payload=None):
        calls.append(method)
        return {}

    monkeypatch.setattr(
        "app.services.user_access_requests.telegram_api.call_bot_api", fake_call_bot_api
    )
    monkeypatch.setattr(
        "app.services.user_access_requests._bot_token", lambda _db: "bot-token"
    )
    monkeypatch.setattr(
        "app.services.user_access_requests.get_feature_service",
        lambda: SimpleNamespace(is_enabled=lambda _key: True),
    )
    assert backfill_request_profile(db, pending_new_user) is False
    assert calls == []
