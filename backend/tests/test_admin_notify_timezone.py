"""AdminNotifyService must resolve timezone from user profile when header is absent."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models import UserRole
from app.services.admin_notify import AdminNotifyService


def test_send_uses_recipient_last_client_timezone_when_no_header(monkeypatch):
    service = AdminNotifyService()
    recipient = SimpleNamespace(
        id=1,
        role=UserRole.admin,
        telegram_id="123",
        timezone="",
        last_client_timezone="Europe/Moscow",
        has_tg_notify_event=lambda _key: True,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [recipient]
    db.query.return_value.filter.return_value.first.return_value = None

    monkeypatch.setattr(
        "app.services.admin_notify.get_feature_service",
        lambda: SimpleNamespace(is_enabled=lambda _k: True),
    )
    monkeypatch.setattr(
        "app.services.admin_notify._get_setting",
        lambda _db, key, default="": {
            "telegram_notify_enabled": "true",
            "telegram_bot_token": "token",
        }.get(key, default),
    )
    monkeypatch.setattr(
        "app.services.admin_notify.filter_notify_recipients",
        lambda _db, users, _getter: users,
    )

    built: dict = {}

    def fake_build(event_type, *args, **kwargs):
        built["client_timezone"] = kwargs.get("client_timezone")
        return "ok"

    monkeypatch.setattr(service, "_build_text", fake_build)
    monkeypatch.setattr(
        "app.services.admin_notify.dispatch_admin_notify",
        lambda *a, **k: None,
    )

    service.send(db, "high_cpu", details="99%")
    assert built["client_timezone"] == "Europe/Moscow"
