"""Clearing relay nodes re-registers the Telegram webhook (otherwise the bot stays silent)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.routers import settings_telegram as st
from app.schemas import TelegramRelayUpdate
from app.services.app_setting_store import _get_setting, _set_setting
import app.database as app_database
from app.services.telegram_transport import current_relay_setting


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


def test_clearing_relay_registers_webhook(monkeypatch, db):
    _set_setting(db, "telegram_bot_token", "tok")
    _set_setting(db, "telegram_bot_interactive_enabled", "true")
    _set_setting(db, st.RELAY_NODES_SETTING, "1")
    db.commit()
    monkeypatch.setattr(app_database, "SessionLocal", sessionmaker(bind=db.get_bind()))
    calls: list[str] = []
    def _set_webhook_spy(token, url, *, secret_token=None):
        assert current_relay_setting() == ""
        calls.append(url)
        return True, ""

    monkeypatch.setattr(st, "set_webhook_sync", _set_webhook_spy)
    monkeypatch.setattr(st, "_configure_bot_menu", lambda _db, _token: None)
    monkeypatch.setattr(st, "_webhook_url", lambda _request, secret: f"https://panel/api/telegram/webhook/{secret}")
    monkeypatch.setattr(st.admin_notify_service, "send_settings_change", lambda *a, **k: None)
    monkeypatch.setattr(st, "_telegram_settings_response", lambda _db, _request: SimpleNamespace())

    st.update_telegram_relay(
        TelegramRelayUpdate(node_ids=[]), SimpleNamespace(headers={}), db, SimpleNamespace(username="admin")
    )

    assert len(calls) == 1
    assert _get_setting(db, st.RELAY_NODES_SETTING) == ""
    assert _get_setting(db, "telegram_webhook_set_at")
    assert _get_setting(db, "telegram_webhook_secret_required") == "true"
