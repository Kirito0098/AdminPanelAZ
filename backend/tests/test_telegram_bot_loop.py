"""Bot updates run on a dedicated loop: blocking handlers must not freeze the panel."""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers import telegram_webhook as tw
from app.services.telegram_bot_loop import BOT_THREAD_NAME, run_on_bot_loop

SECRET = "secret-value-32chars___________"


def test_blocking_handler_does_not_block_caller_loop():
    async def handler():
        time.sleep(0.3)
        return threading.current_thread().name

    async def scenario():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        ticking = asyncio.create_task(ticker())
        thread_name = await run_on_bot_loop(handler())
        ticking.cancel()
        return thread_name, ticks

    thread_name, ticks = asyncio.run(scenario())
    assert thread_name == BOT_THREAD_NAME
    assert ticks >= 5


def test_updates_share_one_bot_loop():
    """The shared httpx.AsyncClient of the bot is bound to the loop it was first used on."""

    async def current_loop():
        return asyncio.get_running_loop()

    async def scenario():
        return await run_on_bot_loop(current_loop()), await run_on_bot_loop(current_loop())

    first, second = asyncio.run(scenario())
    assert first is second


def test_handler_errors_reach_the_caller():
    async def handler():
        raise ValueError("bad update")

    async def scenario():
        await run_on_bot_loop(handler())

    with pytest.raises(ValueError, match="bad update"):
        asyncio.run(scenario())


def test_started_action_survives_caller_cancellation():
    finished = threading.Event()

    async def handler():
        await asyncio.sleep(0.1)
        finished.set()

    async def scenario():
        caller = asyncio.create_task(run_on_bot_loop(handler()))
        await asyncio.sleep(0.02)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller

    asyncio.run(scenario())
    assert finished.wait(1), "a restore or reboot must not be cut off when Telegram drops the request"


class _FakeSession:
    def __init__(self):
        self.closed = threading.Event()
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed.set()


def _allow_webhook(monkeypatch):
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
    monkeypatch.setattr(tw, "claim_telegram_update", lambda _db, _id: True)
    monkeypatch.setattr(tw, "get_settings", lambda: SimpleNamespace(behind_nginx=True))
    monkeypatch.setattr(tw, "resolve_request_url_root", lambda request, behind_nginx: "https://panel.example")
    request = MagicMock()
    request.headers.get = MagicMock(return_value=SECRET)
    request.json = AsyncMock(return_value={"update_id": 1, "message": {}})
    return request


def test_webhook_handles_update_on_bot_loop(monkeypatch):
    request = _allow_webhook(monkeypatch)
    monkeypatch.setattr(tw, "SessionLocal", _FakeSession)
    threads: list[str] = []

    async def handle_update(_db, _update, *, mini_app_url):
        threads.append(threading.current_thread().name)

    monkeypatch.setattr(tw.telegram_bot_service, "handle_update", handle_update)

    assert asyncio.run(tw.telegram_webhook(SECRET, request, MagicMock())) == {"ok": True}
    assert threads == [BOT_THREAD_NAME]


def test_bot_uses_own_session_that_outlives_a_dropped_request(monkeypatch):
    """The request session is closed when the request ends; the bot may still be working."""
    request = _allow_webhook(monkeypatch)
    sessions: list[_FakeSession] = []

    def session_factory():
        sessions.append(_FakeSession())
        return sessions[-1]

    monkeypatch.setattr(tw, "SessionLocal", session_factory)
    request_db = MagicMock()
    started = threading.Event()
    handled_with: list[object] = []

    async def handle_update(db, _update, *, mini_app_url):
        started.set()
        await asyncio.sleep(0.1)
        handled_with.append(db)
        assert not db.closed.is_set()

    monkeypatch.setattr(tw.telegram_bot_service, "handle_update", handle_update)

    async def scenario():
        caller = asyncio.create_task(tw.telegram_webhook(SECRET, request, request_db))
        await asyncio.to_thread(started.wait, 1)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller

    asyncio.run(scenario())
    assert len(sessions) == 1
    assert sessions[0].closed.wait(1), "the bot closes its own session when the update is done"
    assert handled_with == [sessions[0]]


def test_bot_session_rolled_back_and_closed_on_handler_error(monkeypatch):
    request = _allow_webhook(monkeypatch)
    sessions: list[_FakeSession] = []

    def session_factory():
        sessions.append(_FakeSession())
        return sessions[-1]

    monkeypatch.setattr(tw, "SessionLocal", session_factory)

    async def handle_update(_db, _update, *, mini_app_url):
        raise RuntimeError("node unreachable")

    monkeypatch.setattr(tw.telegram_bot_service, "handle_update", handle_update)

    assert asyncio.run(tw.telegram_webhook(SECRET, request, MagicMock())) == {"ok": True}
    assert sessions[0].rolled_back
    assert sessions[0].closed.is_set()
