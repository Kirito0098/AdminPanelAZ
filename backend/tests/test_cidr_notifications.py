"""CIDR pipeline alerts: which statuses reach Telegram and under which event key.

The event key is not cosmetic: the bell picks its category, its level and its
mute preference from it, so a failure notice must not borrow the "rollback
queued" settings key.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.admin_notify import admin_notify_service
from app.services.cidr import cidr_notify


@pytest.fixture
def sent(monkeypatch):
    calls: list[dict] = []

    def fake_send(db, event_type, **kwargs):
        calls.append({"event_type": event_type, **kwargs})

    monkeypatch.setattr(admin_notify_service, "send", fake_send)
    return calls


def _events(sent) -> list[str]:
    return [call["event_type"] for call in sent]


def test_deploy_failure_notifies_cidr_deploy_failed(sent):
    cidr_notify.maybe_notify_deploy_failed(
        MagicMock(),
        {
            "success": False,
            "message": "Развёрнуто на 0 узел(ов)",
            "per_node": [
                {"node_id": 1, "node_name": "ru-1", "status": "failed", "error": "timeout"},
            ],
        },
        triggered_by="manual:admin",
    )

    assert _events(sent) == ["cidr_deploy_failed"]
    assert "ru-1" in sent[0]["details"]
    assert "timeout" in sent[0]["details"]
    assert sent[0]["actor_username"] == "manual:admin"


def test_deploy_success_does_not_notify(sent):
    cidr_notify.maybe_notify_deploy_failed(
        MagicMock(),
        {"success": True, "per_node": [{"node_id": 1, "node_name": "ru-1", "status": "success"}]},
    )

    assert sent == []


def test_ingest_partial_status_notifies_cidr_ingest_partial(sent):
    cidr_notify.maybe_notify_ingest_partial(
        MagicMock(),
        {
            "success": True,
            "status": "partial",
            "providers_updated": 3,
            "providers_failed": 1,
            "per_provider": {"antifilter": {"status": "error"}},
        },
        triggered_by="cron",
    )

    assert _events(sent) == ["cidr_ingest_partial"]
    assert "Обновлено: 3, ошибок: 1" in sent[0]["details"]
    assert "antifilter" in sent[0]["details"]
    assert sent[0]["actor_username"] == "cron"


def test_ingest_ok_status_does_not_notify(sent):
    cidr_notify.maybe_notify_ingest_partial(
        MagicMock(),
        {"success": True, "status": "ok", "providers_updated": 4, "providers_failed": 0},
    )

    assert sent == []


def test_ingest_error_status_notifies(sent):
    cidr_notify.maybe_notify_ingest_partial(
        MagicMock(),
        {
            "success": False,
            "status": "error",
            "providers_updated": 0,
            "providers_failed": 4,
            "per_provider": {"cloudflare": {"status": "error", "error": "HTTP 502"}},
        },
        triggered_by="cron",
    )

    assert _events(sent) == ["cidr_ingest_partial"]
    assert "ошибок: 4" in sent[0]["details"]


def test_ingest_dry_run_does_not_notify(sent):
    cidr_notify.maybe_notify_ingest_partial(
        MagicMock(),
        {
            "success": True,
            "status": "partial",
            "dry_run": True,
            "providers_updated": 1,
            "providers_failed": 1,
        },
    )

    assert sent == []


def test_rollback_failure_uses_its_own_event_key(sent):
    cidr_notify.maybe_notify_rollback_failed(
        MagicMock(),
        {"success": False, "message": "Резервная копия 20260101T000000Z не найдена"},
        triggered_by="manual:admin",
    )

    assert _events(sent) == ["cidr_rollback_failed"]
    assert sent[0]["event_type"] != "settings_cidr_rollback_queued"


def test_rollback_failure_details_list_missing_files(sent):
    cidr_notify.maybe_notify_rollback_failed(
        MagicMock(),
        {"success": False, "missing": ["google-ips.txt", "ovh-ips.txt"]},
    )

    assert len(sent) == 1
    assert "google-ips.txt" in sent[0]["details"]


def test_rollback_success_does_not_notify(sent):
    cidr_notify.maybe_notify_rollback_failed(MagicMock(), {"success": True, "restored": ["a-ips.txt"]})

    assert sent == []
