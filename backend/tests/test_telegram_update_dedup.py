"""Telegram redelivers an update until it gets 2xx; each update_id must run at most once."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import TelegramProcessedUpdate
from app.routers import telegram_webhook as tw
from app.services import retention
from app.services.telegram_update_dedup import PROCESSED_UPDATE_RETENTION, claim_telegram_update

SECRET = "secret-value-32chars___________"


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def webhook(monkeypatch):
    monkeypatch.setattr(tw, "_ensure_telegram_module", lambda: None)
    monkeypatch.setattr(
        tw,
        "_get_setting",
        lambda db, key, default="": {
            "telegram_bot_interactive_enabled": "true",
            "telegram_webhook_secret": SECRET,
        }.get(key, default),
    )
    monkeypatch.setattr(tw, "get_telegram_webhook_client_ip", lambda _r: "149.154.160.1")
    monkeypatch.setattr(tw, "is_telegram_ip", lambda _ip: True)
    monkeypatch.setattr(tw, "consume_webhook_rate_limit", lambda _ip: None)
    monkeypatch.setattr(tw, "get_settings", lambda: SimpleNamespace(behind_nginx=True))
    monkeypatch.setattr(tw, "resolve_request_url_root", lambda request, behind_nginx: "https://panel.example")
    monkeypatch.setattr(tw, "SessionLocal", MagicMock)
    handle = AsyncMock()
    monkeypatch.setattr(tw.telegram_bot_service, "handle_update", handle)
    return handle


def _post(db, payload):
    request = MagicMock()
    request.headers.get = MagicMock(return_value=SECRET)
    request.json = AsyncMock(return_value=payload)
    return asyncio.run(tw.telegram_webhook(SECRET, request, db))


def test_claim_telegram_update_only_once(db):
    assert claim_telegram_update(db, 1001) is True
    assert claim_telegram_update(db, 1001) is False
    assert claim_telegram_update(db, 1002) is True


def test_claim_telegram_update_without_id_is_processed(db):
    assert claim_telegram_update(db, None) is True
    assert claim_telegram_update(db, "1") is True
    assert db.query(TelegramProcessedUpdate).count() == 0


def test_claim_telegram_update_does_not_purge_on_every_update(db):
    db.add(TelegramProcessedUpdate(update_id=5, received_at=datetime.utcnow() - timedelta(days=30)))
    db.commit()
    assert claim_telegram_update(db, 6) is True
    assert {row.update_id for row in db.query(TelegramProcessedUpdate).all()} == {5, 6}


def test_retention_purges_processed_updates_older_than_the_window(db, monkeypatch):
    monkeypatch.setattr(
        retention,
        "get_settings",
        lambda: SimpleNamespace(
            retention_batch_size=100,
            traffic_sample_retention_days=90,
            action_log_retention_days=365,
            resource_metrics_retention_days=30,
            panel_resource_metrics_retention_days=30,
            traffic_session_retention_days=30,
        ),
    )
    now = retention._utcnow()
    window = PROCESSED_UPDATE_RETENTION
    db.add_all(
        [
            TelegramProcessedUpdate(update_id=1, received_at=now - window - timedelta(minutes=1)),
            TelegramProcessedUpdate(update_id=2, received_at=now - window + timedelta(minutes=5)),
            TelegramProcessedUpdate(update_id=3, received_at=now),
        ]
    )
    db.commit()

    counts = retention.run_retention_purge(db)

    assert counts["telegram_processed_updates"] == 1
    assert {row.update_id for row in db.query(TelegramProcessedUpdate).all()} == {2, 3}
    assert claim_telegram_update(db, 2) is False


def test_webhook_redelivered_update_handled_once(db, webhook):
    payload = {"update_id": 42, "callback_query": {"data": "st:bk:do:rst:0"}}

    assert _post(db, payload) == {"ok": True}
    assert _post(db, payload) == {"ok": True}

    webhook.assert_awaited_once()


def test_webhook_handler_error_still_acknowledged(db, webhook):
    webhook.side_effect = RuntimeError("boom")

    assert _post(db, {"update_id": 43}) == {"ok": True}
    webhook.side_effect = None
    assert _post(db, {"update_id": 43}) == {"ok": True}

    webhook.assert_awaited_once()


def test_webhook_rejects_non_object_payload(db, webhook):
    with pytest.raises(HTTPException) as exc:
        _post(db, [1, 2, 3])
    assert exc.value.status_code == 400
    webhook.assert_not_awaited()
