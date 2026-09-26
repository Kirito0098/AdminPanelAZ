"""Dedicated event loop thread for Telegram bot updates.

Bot handlers mix awaits with blocking calls (DB, node agents, backup restore).
Running them here keeps the panel's event loop responsive; bot updates wait for
each other instead of every panel request waiting for the bot.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

BOT_THREAD_NAME = "telegram-bot"

_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None


def _bot_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    with _lock:
        if _loop is None or _thread is None or not _thread.is_alive():
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, name=BOT_THREAD_NAME, daemon=True)
            thread.start()
            _loop, _thread = loop, thread
        return _loop


async def run_on_bot_loop(coro: Coroutine[Any, Any, T]) -> T:
    future = asyncio.run_coroutine_threadsafe(coro, _bot_loop())
    # Telegram may drop a slow webhook request; a started restore or reboot must still finish.
    return await asyncio.shield(asyncio.wrap_future(future))
