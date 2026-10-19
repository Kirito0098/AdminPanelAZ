"""Stage 4 Task 6: уведомления в Telegram о массовых операциях с серверами.

TDD: сообщение уходит только в личный чат пользователя и только после
успешной части операции; 403 (бот заблокирован) — «не доставлено», без
повторов; отправка ограничена ~20 сообщениями в секунду.
"""

from types import SimpleNamespace

import pytest

from app.services.bulk_user_nodes_notify import (
    TELEGRAM_BULK_RATE_PER_SEC,
    TelegramBulkThrottle,
    maybe_notify_after_user,
    render_bulk_notify_text,
    send_bulk_user_notify,
)


def _result(**kwargs):
    base = {
        "user_id": 1,
        "username": "ivan",
        "status": "ok",
        "skip_reason": None,
        "created": 1,
        "deleted": 0,
        "error": None,
        "replaced": False,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _user(telegram_id=None):
    return SimpleNamespace(id=1, username="ivan", telegram_id=telegram_id)


# --- тексты ---------------------------------------------------------------


def test_render_add_text_includes_label_and_note():
    text = render_bulk_notify_text(
        "add", node_label="Finland", to_node_label=None, note="Обновите приложение"
    )
    assert "Finland" in text
    assert "Обновите приложение" in text


def test_render_remove_text_mentions_remaining_server():
    text = render_bulk_notify_text(
        "remove",
        node_label="Germany",
        to_node_label=None,
        note=None,
        remaining_labels=["Finland"],
    )
    assert "Germany" in text
    assert "Finland" in text


def test_render_replace_text_mentions_both_servers():
    text = render_bulk_notify_text(
        "replace", node_label="Germany", to_node_label="Finland", note=None
    )
    assert "Germany" in text
    assert "Finland" in text


# --- доставка -------------------------------------------------------------


def test_send_skips_without_calling_telegram_when_no_id(monkeypatch):
    called = []
    monkeypatch.setattr(
        "app.services.bulk_user_nodes_notify.send_tg_message_result",
        lambda *a, **k: called.append(1) or (True, None),
    )
    status = maybe_notify_after_user(
        enabled=True,
        user=_user(telegram_id=None),
        result=_result(),
        action="add",
        node_label="Finland",
        bot_token="token",
    )
    assert status == "no_telegram"
    assert called == []


def test_send_once_on_success_only(monkeypatch):
    called = []
    monkeypatch.setattr(
        "app.services.bulk_user_nodes_notify.send_tg_message_result",
        lambda *a, **k: called.append(1) or (True, None),
    )
    status = maybe_notify_after_user(
        enabled=True,
        user=_user(telegram_id="42"),
        result=_result(status="failed"),
        action="add",
        node_label="Finland",
        bot_token="token",
    )
    assert status == "skipped_status"
    assert called == []


def test_add_without_created_config_is_not_notified(monkeypatch):
    called = []
    monkeypatch.setattr(
        "app.services.bulk_user_nodes_notify.send_tg_message_result",
        lambda *a, **k: called.append(1) or (True, None),
    )
    # Истёкший доступ: присвоение изменилось, но конфиги не создавались.
    status = maybe_notify_after_user(
        enabled=True,
        user=_user(telegram_id="42"),
        result=_result(created=0),
        action="add",
        node_label="Finland",
        bot_token="token",
    )
    assert status == "skipped_no_create"
    assert called == []


def test_notify_disabled_sends_nothing(monkeypatch):
    called = []
    monkeypatch.setattr(
        "app.services.bulk_user_nodes_notify.send_tg_message_result",
        lambda *a, **k: called.append(1) or (True, None),
    )
    status = maybe_notify_after_user(
        enabled=False,
        user=_user(telegram_id="42"),
        result=_result(),
        action="add",
        node_label="Finland",
        bot_token="token",
    )
    assert status == "disabled"
    assert called == []


def test_notify_sent_to_own_chat_only(monkeypatch):
    seen = {}

    def fake_send(bot_token, chat_id, text):
        seen["chat_id"] = chat_id
        seen["text"] = text
        return True, None

    monkeypatch.setattr(
        "app.services.bulk_user_nodes_notify.send_tg_message_result", fake_send
    )
    status = maybe_notify_after_user(
        enabled=True,
        user=_user(telegram_id="42"),
        result=_result(),
        action="add",
        node_label="Finland",
        bot_token="token",
    )
    assert status == "sent"
    assert seen["chat_id"] == "42"
    assert "Finland" in seen["text"]


def test_telegram_403_is_undelivered_not_raised(monkeypatch):
    monkeypatch.setattr(
        "app.services.bulk_user_nodes_notify.send_tg_message_result",
        lambda *a, **k: (False, 403),
    )
    assert (
        send_bulk_user_notify(bot_token="t", telegram_id=1, text="x", portal_url=None)
        == "undelivered"
    )


def test_telegram_other_error_is_error(monkeypatch):
    monkeypatch.setattr(
        "app.services.bulk_user_nodes_notify.send_tg_message_result",
        lambda *a, **k: (False, 500),
    )
    assert (
        send_bulk_user_notify(bot_token="t", telegram_id=1, text="x", portal_url=None)
        == "error"
    )


def test_portal_url_appended_to_message(monkeypatch):
    seen = {}

    def fake_send(bot_token, chat_id, text):
        seen["text"] = text
        return True, None

    monkeypatch.setattr(
        "app.services.bulk_user_nodes_notify.send_tg_message_result", fake_send
    )
    send_bulk_user_notify(
        bot_token="t",
        telegram_id=1,
        text="Добавлен новый сервер Finland.",
        portal_url="https://portal.example.com/p/abc",
    )
    assert "https://portal.example.com/p/abc" in seen["text"]


# --- троттлинг ------------------------------------------------------------


def test_throttle_sleeps_between_sends(monkeypatch):
    sleeps = []
    monkeypatch.setattr(
        "app.services.bulk_user_nodes_notify.time.sleep", sleeps.append
    )
    throttle = TelegramBulkThrottle(rate=20)
    throttle.send(lambda: "sent")
    throttle.send(lambda: "sent")
    assert sleeps and sleeps[0] == pytest.approx(1 / 20, rel=0.2)


def test_throttle_default_rate_is_20():
    assert TELEGRAM_BULK_RATE_PER_SEC == 20
