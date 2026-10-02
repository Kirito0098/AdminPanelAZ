"""HA drift found by the reconcile worker reaches the admin notification."""

import json
from unittest.mock import MagicMock

from app.models import User
from app.services.admin_notify import (
    TG_NOTIFY_EVENT_LABELS,
    admin_notify_service,
    build_notify_event_preview_text,
)
from app.services.node_sync import reconcile_worker


def test_drift_notify_reaches_admin_notify(monkeypatch):
    sent = []
    monkeypatch.setattr(admin_notify_service, "send", lambda db, event_type, **kw: sent.append((event_type, kw)))
    monkeypatch.setattr(reconcile_worker, "SessionLocal", lambda: MagicMock())
    drift = {"group_id": 1, "issues": ["x"]}

    reconcile_worker._notify_drift([drift])

    assert len(sent) == 1
    event_type, kwargs = sent[0]
    assert event_type == "node_sync_drift"
    assert json.loads(kwargs["details"]) == drift


def test_drift_notify_text_names_group_summary_and_hint():
    details = json.dumps(
        {
            "group_id": 3,
            "name": "ha-<eu>",
            "shared_domain": "vpn.example.com",
            "summary": "OpenVPN: 2 клиента",
            "hint": "Автолечение приостановлено",
        },
        ensure_ascii=False,
    )

    text = admin_notify_service._build_text("node_sync_drift", None, None, None, None, details)

    assert "HA: расхождение" in text
    assert "ha-&lt;eu&gt;" in text
    assert "vpn.example.com" in text
    assert "OpenVPN: 2 клиента" in text
    assert "Автолечение приостановлено" in text
    assert "Администратор" not in text
    assert "Изменение" not in text


def test_drift_notify_text_tolerates_bad_details():
    text = admin_notify_service._build_text("node_sync_drift", None, None, None, None, "not json")

    assert "HA: расхождение" in text


def test_drift_is_its_own_notify_type_with_preview():
    assert "node_sync_drift" in dict(TG_NOTIFY_EVENT_LABELS)
    assert "HA: расхождение" in build_notify_event_preview_text("node_sync_drift")


def _user_with_prefs(prefs: dict | None) -> User:
    user = User(username="admin")
    user.tg_notify_events = json.dumps(prefs) if prefs is not None else None
    return user


def test_drift_pref_defaults_on_without_saved_prefs():
    user = _user_with_prefs(None)

    assert user.has_tg_notify_event("node_sync_drift") is True
    assert user.merged_tg_notify_events()["node_sync_drift"] is True


def test_drift_pref_inherits_settings_change_when_not_saved_yet():
    muted = _user_with_prefs({"settings_change": False, "login_success": True})
    subscribed = _user_with_prefs({"settings_change": True, "login_success": True})

    assert muted.has_tg_notify_event("node_sync_drift") is False
    assert muted.merged_tg_notify_events()["node_sync_drift"] is False
    assert subscribed.has_tg_notify_event("node_sync_drift") is True
    assert subscribed.merged_tg_notify_events()["node_sync_drift"] is True


def test_drift_pref_saved_value_wins_over_settings_change():
    only_drift = _user_with_prefs({"settings_change": False, "node_sync_drift": True})
    no_drift = _user_with_prefs({"settings_change": True, "node_sync_drift": False})

    assert only_drift.has_tg_notify_event("node_sync_drift") is True
    assert no_drift.has_tg_notify_event("node_sync_drift") is False
    assert no_drift.has_tg_notify_event("settings_change") is True
