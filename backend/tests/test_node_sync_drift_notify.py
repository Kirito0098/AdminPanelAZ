"""HA drift found by the reconcile worker reaches the admin notification."""

import json
from unittest.mock import MagicMock

from app.services.admin_notify import admin_notify_service
from app.services.node_sync import reconcile_worker


def test_drift_notify_reaches_admin_notify(monkeypatch):
    sent = []
    monkeypatch.setattr(admin_notify_service, "send", lambda db, event_type, **kw: sent.append((event_type, kw)))
    monkeypatch.setattr(reconcile_worker, "SessionLocal", lambda: MagicMock())
    drift = {"group_id": 1, "issues": ["x"]}

    reconcile_worker._notify_drift([drift])

    assert len(sent) == 1
    event_type, kwargs = sent[0]
    assert event_type == "settings_change"
    assert kwargs["target_name"] == "node_sync_drift"
    assert json.loads(kwargs["details"]) == drift


def test_drift_notify_text_names_group_summary_and_hint():
    details = json.dumps(
        {"group_id": 3, "name": "ha-<eu>", "summary": "OpenVPN: 2 клиента", "hint": "Автолечение приостановлено"},
        ensure_ascii=False,
    )

    text = admin_notify_service._build_text("settings_change", "system", "node_sync_drift", None, None, details)

    assert "HA: расхождение" in text
    assert "Расхождение в HA-группе «ha-&lt;eu&gt;»: OpenVPN: 2 клиента. Автолечение приостановлено" in text
