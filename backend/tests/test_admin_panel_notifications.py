"""Bell notification rows must be human-readable, not raw event types and JSON."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AdminPanelNotification
from app.services import admin_notify as notify_module
from app.services.admin_panel_notifications import bell_title, humanize_bell_message
from app.services.admin_notify import AdminNotifyService

DRIFT_DETAILS = json.dumps(
    {
        "group_id": 1,
        "name": "Test",
        "shared_domain": "vpn.claymore.com",
        "summary": "Расхождения между узлами",
    },
    ensure_ascii=False,
)


def test_bell_title_is_human_for_known_events():
    assert bell_title("node_sync_drift") == "HA: расхождение узлов"
    assert bell_title("config_create") == "Создан конфиг"


def test_bell_title_falls_back_to_a_readable_phrase():
    assert bell_title("some_new_event") == "Some new event"


def test_details_json_becomes_labelled_lines():
    message = humanize_bell_message(DRIFT_DETAILS)

    assert "Группа: Test" in message
    assert "Домен: vpn.claymore.com" in message
    assert "Расхождения: Расхождения между узлами" in message
    assert "{" not in message and '"' not in message


def test_key_value_details_get_labels():
    assert humanize_bell_message("username=bob") == "Пользователь: bob"


def test_empty_details_give_an_empty_message():
    assert humanize_bell_message(None) == ""
    assert humanize_bell_message("   ") == ""


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    session = make()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_send_writes_a_readable_bell_row(db, monkeypatch):
    class _Features:
        def is_enabled(self, _name):
            return False

    monkeypatch.setattr(notify_module, "get_feature_service", lambda: _Features())
    service = AdminNotifyService()

    service.send(db, "node_sync_drift", details=DRIFT_DETAILS, node_name="1Cent-EE")

    row = db.query(AdminPanelNotification).one()
    assert row.title == "HA: расхождение узлов"
    assert "Группа: Test" in row.message
    assert "Узел: 1Cent-EE" in row.message
    assert "{" not in row.message
