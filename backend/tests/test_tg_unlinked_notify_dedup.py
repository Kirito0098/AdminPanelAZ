"""Unlinked Telegram login notify must not spam duplicates."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.services.admin_notify import AdminNotifyService


def test_send_tg_login_unlinked_dedupes_within_cooldown(monkeypatch):
    service = AdminNotifyService()
    calls: list[tuple] = []

    def fake_send(db, event_type, **kwargs):
        calls.append((event_type, kwargs.get("target_name")))

    monkeypatch.setattr(service, "send", fake_send)
    db = MagicMock()

    service.send_tg_login_unlinked(db, telegram_id="6028369631", mini=True)
    service.send_tg_login_unlinked(db, telegram_id="6028369631", mini=True)
    service.send_tg_login_unlinked(db, telegram_id="6028369631", mini=False)

    assert calls == [("tg_mini_login_unlinked", "6028369631")]


def test_send_tg_login_unlinked_allows_after_cooldown(monkeypatch):
    service = AdminNotifyService()
    calls: list[str] = []
    monkeypatch.setattr(service, "send", lambda *a, **k: calls.append(k.get("target_name", "")))
    db = MagicMock()

    service.send_tg_login_unlinked(db, telegram_id="111", mini=True)
    # Expire cooldown
    service._unlinked_login_cooldowns["111"] = datetime.now(timezone.utc) - timedelta(seconds=61)
    service.send_tg_login_unlinked(db, telegram_id="111", mini=True)

    assert calls == ["111", "111"]


def test_send_tg_login_unlinked_different_ids_not_deduped(monkeypatch):
    service = AdminNotifyService()
    calls: list[str] = []
    monkeypatch.setattr(service, "send", lambda *a, **k: calls.append(k.get("target_name", "")))
    db = MagicMock()

    service.send_tg_login_unlinked(db, telegram_id="1", mini=True)
    service.send_tg_login_unlinked(db, telegram_id="2", mini=True)

    assert calls == ["1", "2"]


def test_send_tg_login_unlinked_ignores_blank_id(monkeypatch):
    service = AdminNotifyService()
    called = MagicMock()
    monkeypatch.setattr(service, "send", called)
    service.send_tg_login_unlinked(MagicMock(), telegram_id="  ", mini=True)
    called.assert_not_called()
