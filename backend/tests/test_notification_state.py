"""Состояние уведомлений личное: скрытие, отложенное и прочтение одного админа не видны другому."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AdminPanelNotification, User, UserRole
from app.services.admin_notify import AdminNotifyService
from app.services.admin_panel_notifications import (
    list_notifications_for_admin,
    set_notification_state,
    write_admin_panel_notification,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def env(db):
    first = User(username="first", password_hash="x", role=UserRole.admin)
    second = User(username="second", password_hash="x", role=UserRole.admin)
    db.add_all([first, second])
    db.flush()
    for index, (category, level) in enumerate(
        [("requests", "info"), ("security", "error"), ("nodes", "info")], start=1
    ):
        db.add(
            AdminPanelNotification(
                id=index,
                category=category,
                level=level,
                event_type="login_failed",
                title=f"Событие {index}",
                message="детали",
                created_at=datetime.utcnow(),
            )
        )
    db.commit()
    return db, first, second


def test_state_is_per_admin(env):
    db, first, second = env

    items, unread, counts = list_notifications_for_admin(db, second, limit=10)
    assert unread == 3 and counts["unread"] == 3
    assert len(items) == 3

    set_notification_state(db, first, 1, hidden=True)
    set_notification_state(db, first, 2, snoozed_until=datetime.utcnow() + timedelta(hours=3))
    set_notification_state(db, first, 3, read=True)

    first_items, first_unread, first_counts = list_notifications_for_admin(db, first, limit=10)
    assert [item["id"] for item in first_items] == [3, 2]
    assert first_unread == 0  # 1 скрыто, 2 отложено, 3 прочитано
    assert first_counts["hidden"] == 1
    assert first_counts["snoozed"] == 1

    second_items, second_unread, second_counts = list_notifications_for_admin(db, second, limit=10)
    assert [item["id"] for item in second_items] == [3, 2, 1]
    assert second_unread == 3
    assert second_counts["hidden"] == 0
    assert [item["state"]["read"] for item in second_items] == [False, False, False]

    hidden_items, _, _ = list_notifications_for_admin(db, first, hidden_only=True, limit=10)
    assert [item["id"] for item in hidden_items] == [1]

    set_notification_state(db, first, 1, hidden=False)
    restored_items, restored_unread, _ = list_notifications_for_admin(db, first, limit=10)
    assert [item["id"] for item in restored_items] == [3, 2, 1]
    assert restored_unread == 1  # вернулось только скрытое; 2 всё ещё отложено, 3 прочитано
def test_watermark_marks_items_read(env):
    """Водяной знак — тоже прочтение: API обязан отдавать state.read=true для id <= last_read.

    Иначе карточка выглядит непрочитанной (бейдж считает по водяному знаку, а карточка —
    по state.read), и «Отметить всё» визуально ничего не делает.
    """
    db, first, _ = env
    first.last_read_notification_id = 3
    db.add(first)
    db.commit()

    items, unread, counts = list_notifications_for_admin(db, first, limit=10)

    assert unread == 0 and counts["unread"] == 0
    assert [item["state"]["read"] for item in items] == [True, True, True]

    # Частичный водяной знак: прочитано только до 2.
    first.last_read_notification_id = 2
    db.add(first)
    db.commit()

    items, unread, _ = list_notifications_for_admin(db, first, limit=10)
    assert unread == 1
    assert [item["state"]["read"] for item in items] == [False, True, True]


    assert set_notification_state(db, first, 999, read=True) is None


def test_unread_only_fills_the_page_when_newest_are_read(env):
    """Непрочитанные не должны теряться за прочитанными: окно выборки шире страницы.

    Колокол просит 5 непрочитанных. Если читать только верхние 5 строк, отметка
    «прочитано» на них вернёт пустой список при живом бейдже «N новых».
    """
    db, first, _ = env
    for index in range(4, 9):
        db.add(
            AdminPanelNotification(
                id=index,
                category="nodes",
                level="info",
                event_type="login_failed",
                title=f"Событие {index}",
                message="детали",
                created_at=datetime.utcnow(),
            )
        )
    db.commit()

    # Верхние две из восьми помечены прочитанными поштучно, как после кнопки ✓ в колоколе.
    set_notification_state(db, first, 8, read=True)
    set_notification_state(db, first, 7, read=True)

    items, unread, _ = list_notifications_for_admin(db, first, unread_only=True, limit=3)

    assert [item["id"] for item in items] == [6, 5, 4]
    assert unread == 6


def test_author_action_is_read_for_author_only(env):
    """Своё действие не висит у автора непрочитанным, но остаётся в истории и у остальных."""
    db, first, second = env

    row = write_admin_panel_notification(
        db,
        event_type="user_delete",
        title="Удалён пользователь",
        message="Кто: first · Объект: ivan",
        read_for_username=first.username,
    )
    assert row is not None

    first_items, first_unread, _ = list_notifications_for_admin(db, first, limit=10)
    second_items, second_unread, _ = list_notifications_for_admin(db, second, limit=10)

    assert first_unread == 3
    assert second_unread == 4
    assert [item["state"]["read"] for item in first_items if item["id"] == row.id] == [True]
    assert [item["state"]["read"] for item in second_items if item["id"] == row.id] == [False]


def test_actor_does_not_get_own_action_unread(env):
    """Отправитель не получает своё действие как новое, но попытку входа — получает."""
    db, first, second = env
    service = AdminNotifyService()

    service.send(db, "user_delete", actor_username=first.username, target_name="ivan")
    service.send(db, "login_failed", actor_username=first.username, remote_addr="10.0.0.1")

    _, first_unread, _ = list_notifications_for_admin(db, first, limit=10)
    _, second_unread, _ = list_notifications_for_admin(db, second, limit=10)

    # user_delete — read_for_username, login_failed — security-событие: автор должен его видеть.
    assert first_unread == 4
    assert second_unread == 5


def test_deferred_settings_result_stays_new_for_author(env):
    """Результат отложенной перезагрузки — не «своё действие»: провал должен дойти автору."""
    db, first, _ = env
    service = AdminNotifyService()

    service.send_settings_change(
        db,
        actor_username=first.username,
        settings_key="settings_reboot_execute",
        subject_name="node (ошибка)",
        details="node_id=1 node=node status=failed error=timeout",
        read_for_author=False,
    )

    items, first_unread, _ = list_notifications_for_admin(db, first, limit=10)
    assert first_unread == 4
    assert items[0]["event_type"] == "settings_change"
    assert items[0]["state"]["read"] is False


def test_background_result_is_read_for_author_only_when_clean(env):
    """Успешный результат фоновой задачи автору прочитан, провал — нет."""
    db, first, second = env
    service = AdminNotifyService()

    service.send(
        db,
        "user_provision_applied",
        actor_username=first.username,
        target_name="ivan",
        details="ivan: создано 3, удалено 0, ошибок 0",
        read_for_author=True,
    )
    service.send(
        db,
        "user_provision_applied",
        actor_username=first.username,
        target_name="petr",
        details="petr: создано 3, удалено 0, ошибок 2",
        read_for_author=False,
    )

    _, first_unread, _ = list_notifications_for_admin(db, first, limit=10)
    _, second_unread, _ = list_notifications_for_admin(db, second, limit=10)

    assert first_unread == 4
    assert second_unread == 5
