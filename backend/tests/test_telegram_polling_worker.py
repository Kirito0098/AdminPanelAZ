"""Long polling through the relay node feeds the webhook handler."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services import telegram_polling_worker as worker
from app.services.app_setting_store import _get_setting, _set_setting


@pytest.fixture
def factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        _set_setting(db, "telegram_bot_token", "123456:" + "A" * 35)
        _set_setting(db, "telegram_bot_interactive_enabled", "true")
        _set_setting(db, "telegram_relay_node_ids", "1")
        _set_setting(db, "telegram_mini_app_url", "https://panel.example/api/tg-mini")
        _set_setting(db, "telegram_relay_last_error", "старая ошибка")
        db.commit()
    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(worker, "_telegram_module_enabled", lambda: True)
    yield factory
    engine.dispose()


def test_poll_once_handles_new_updates_once_and_advances_offset(factory, monkeypatch):
    handled: list[int] = []
    requests: list[dict] = []

    async def fake_post(_token, method, *, json=None, timeout=None):
        requests.append(json)
        return {"ok": True, "result": [{"update_id": 7}, {"update_id": 8}, {"update_id": 7}]}

    async def fake_handle(update, *, mini_app_url):
        assert mini_app_url == "https://panel.example/api/tg-mini"
        handled.append(update["update_id"])

    async def run_inline(coro):
        return await coro

    monkeypatch.setattr(worker, "bot_api_post", fake_post)
    monkeypatch.setattr(worker, "_handle_update", fake_handle)
    monkeypatch.setattr(worker, "run_on_bot_loop", run_inline)

    offset = asyncio.run(worker.poll_once(5))

    assert offset == 9
    assert handled == [7, 8]
    assert requests[0]["offset"] == 5
    with factory() as db:
        assert _get_setting(db, "telegram_relay_last_ok_at")
        assert _get_setting(db, "telegram_relay_last_error") == ""
