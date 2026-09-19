from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, User, UserReminderLog, UserRole, VpnConfig, VpnType
from app.services import user_reminder_service as reminders
from app.services.admin_notify import PERSONAL_OWNER_NOTIFY_KEYS, TG_NOTIFY_EVENT_LABELS, AdminNotifyService, build_notify_event_preview_text


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _make_user(db, *, username: str, access_until: datetime | None = None, telegram_id: str | None = "100") -> User:
    user = User(
        username=username,
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        telegram_id=telegram_id,
        access_until=access_until.replace(tzinfo=None) if access_until else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_node(db) -> Node:
    node = Node(
        name="node-1",
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=True,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _patch_reminder_runtime(monkeypatch):
    monkeypatch.setattr(reminders, "self_service_reminder_enabled", lambda: True)
    monkeypatch.setattr(reminders, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda _key: True))
    monkeypatch.setattr(
        reminders,
        "get_settings",
        lambda: SimpleNamespace(
            self_service_reminder_access_days_threshold=7,
            self_service_reminder_cert_days_threshold=7,
            self_service_traffic_warning_percent=90,
            antizapret_path=Path("/tmp/antizapret"),
        ),
    )
    monkeypatch.setattr(
        reminders,
        "_get_setting",
        lambda _db, key, default="": "token" if key == "telegram_bot_token" else default,
    )
    owner_messages: list[dict] = []
    admin_calls: list[dict] = []
    monkeypatch.setattr(
        reminders,
        "send_tg_message",
        lambda _token, chat_id, text, **_kw: owner_messages.append({"chat_id": chat_id, "text": text}) or True,
    )

    def fake_admin_send(_db, event_type, **kwargs):
        admin_calls.append({"event_type": event_type, **kwargs})

    monkeypatch.setattr(reminders.admin_notify_service, "send", fake_admin_send)
    return owner_messages, admin_calls


def test_process_user_reminders_sends_access_expiry_once_per_deadline(db, monkeypatch):
    now = datetime.now(timezone.utc)
    owner = _make_user(db, username="owner-access", access_until=now + timedelta(days=3))
    owner_messages, admin_calls = _patch_reminder_runtime(monkeypatch)
    expected_days = reminders.days_remaining_until(owner.access_until)

    sent = reminders.process_user_reminders(db)

    assert sent == 1
    assert len(owner_messages) == 1
    assert "Доступ скоро истечёт" in owner_messages[0]["text"]
    assert owner.access_until.date().isoformat() in owner_messages[0]["text"]
    assert admin_calls == [
        {
            "event_type": "user_access_expiry_reminder",
            "actor_username": "owner-access",
            "target_name": None,
            "target_type": None,
            "details": f"Доступ до <code>{owner.access_until.date().isoformat()}</code>, осталось <b>{expected_days}</b> дн.",
            "subject_name": "owner-access",
            "node_id": None,
            "client_timezone": None,
        }
    ]
    log = db.query(UserReminderLog).filter_by(user_id=owner.id, reminder_type=reminders.REMINDER_ACCESS).one()
    assert log.dedup_key == f"user:{owner.id}:access:{owner.access_until.date().isoformat()}"

    sent_again = reminders.process_user_reminders(db)

    assert sent_again == 0
    assert len(owner_messages) == 1
    assert len(admin_calls) == 1


def test_process_user_reminders_keeps_access_and_cert_paths_independent(db, monkeypatch):
    now = datetime.now(timezone.utc)
    owner = _make_user(db, username="owner-both", access_until=now + timedelta(days=3))
    node = _make_node(db)
    db.add(
        VpnConfig(
            node_id=node.id,
            client_name="demo-ovpn",
            vpn_type=VpnType.openvpn,
            owner_id=owner.id,
            cert_expires_at=(now + timedelta(days=2)).replace(tzinfo=None),
        )
    )
    db.commit()

    owner_messages, admin_calls = _patch_reminder_runtime(monkeypatch)
    monkeypatch.setattr(reminders, "get_adapter_for_node", lambda _node: MagicMock())

    class DummyPolicyService:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_openvpn_policy(self, _client_name: str) -> dict:
            return {}

        def get_wg_policy(self, _client_name: str) -> dict:
            return {}

    monkeypatch.setattr(reminders, "AccessPolicyService", DummyPolicyService)

    sent = reminders.process_user_reminders(db)

    assert sent == 2
    assert len(owner_messages) == 2
    assert any("Доступ скоро истечёт" in message["text"] for message in owner_messages)
    assert any("Сертификат скоро истечёт" in message["text"] for message in owner_messages)
    assert [call["event_type"] for call in admin_calls] == [
        "user_access_expiry_reminder",
        "user_cert_expiry_reminder",
    ]
    reminder_types = {
        row.reminder_type
        for row in db.query(UserReminderLog).filter(UserReminderLog.user_id == owner.id).all()
    }
    assert reminder_types == {reminders.REMINDER_ACCESS, reminders.REMINDER_CERT}


def test_access_expiry_events_are_exposed_in_notify_metadata():
    labels = dict(TG_NOTIFY_EVENT_LABELS)
    assert labels["access_expiry_reminder"] == "Напоминание: срок доступа"
    assert labels["user_access_expiry_reminder"] == "Пользователь: срок доступа"
    assert "access_expiry_reminder" in PERSONAL_OWNER_NOTIFY_KEYS

    owner_preview = build_notify_event_preview_text("access_expiry_reminder")
    assert owner_preview is not None
    assert "Доступ скоро истечёт" in owner_preview

    admin_preview = AdminNotifyService()._build_text(
        "user_access_expiry_reminder",
        "owner-access",
        None,
        None,
        None,
        "Доступ до <code>2026-07-10</code>, осталось <b>5</b> дн.",
        "owner-access",
    )
    assert admin_preview is not None
    assert "Доступ пользователя" in admin_preview
    assert "👤 Пользователь" in admin_preview
    assert "📁 Клиент" not in admin_preview
