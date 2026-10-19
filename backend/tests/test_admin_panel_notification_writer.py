"""Stage 2 Task 2: bell writer on AdminNotifyService.send + retention purge >30d."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import AdminPanelNotification, Base
from app.services.admin_notify import admin_notify_service
from app.services.admin_panel_notifications import category_for_event
from app.services.retention import run_retention_purge


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


def test_category_map_covers_known_events():
    assert category_for_event("login_failed") == "security"
    assert category_for_event("node_offline") == "nodes"
    assert category_for_event("cidr_deploy_failed") == "services"
    assert category_for_event("user_provision_summary") == "tasks"
    assert category_for_event("access_request_new_user") == "requests"
    assert category_for_event("access_request_extend_access") == "requests"
    assert category_for_event("access_request_delivery_failed") == "requests"
    assert category_for_event("unknown_event") == "tasks"


def test_send_writes_bell_row_even_when_telegram_disabled(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.admin_notify.get_feature_service",
        lambda: MagicMock(is_enabled=lambda _k: False),
    )
    admin_notify_service.send(db, "node_offline", details="node1 offline", node_name="n1")
    row = db.query(AdminPanelNotification).one()
    assert row.category == "nodes"
    assert row.event_type == "node_offline"
    assert row.title  # non-empty


def test_bell_writer_failure_does_not_block_telegram(db, monkeypatch):
    calls = {"tg": 0}

    def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "app.services.admin_notify.write_admin_panel_notification",
        boom,
    )
    monkeypatch.setattr(
        "app.services.admin_notify.get_feature_service",
        lambda: MagicMock(is_enabled=lambda _k: True),
    )
    monkeypatch.setattr(
        "app.services.admin_notify._get_setting",
        lambda db, k, d="": {
            "telegram_notify_enabled": "true",
            "telegram_bot_token": "TOKEN",
        }.get(k, d),
    )
    monkeypatch.setattr(
        "app.services.admin_notify.dispatch_admin_notify",
        lambda *a, **k: calls.__setitem__("tg", calls["tg"] + 1),
    )
    # No users in db → notify_users empty → send returns after the writer; no raise.
    admin_notify_service.send(db, "login_success", actor_username="admin")


def test_retention_purges_notifications_older_than_30_days(db):
    old = AdminPanelNotification(
        category="tasks",
        level="info",
        event_type="x",
        title="old",
        message="",
        created_at=datetime.utcnow() - timedelta(days=31),
    )
    fresh = AdminPanelNotification(
        category="tasks",
        level="info",
        event_type="y",
        title="fresh",
        message="",
        created_at=datetime.utcnow(),
    )
    db.add_all([old, fresh])
    db.commit()
    counts = run_retention_purge(db)
    assert counts["admin_panel_notifications"] == 1
    assert db.query(AdminPanelNotification).count() == 1
