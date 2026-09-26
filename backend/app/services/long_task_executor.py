"""Threads for long scheduled jobs: auto-backup, CIDR refresh, retention purge.

``asyncio.to_thread`` uses the default executor (min(32, CPUs + 4) threads), which every
monitoring loop shares. A job that archives the DB or downloads provider lists for minutes
would hold those threads and delay monitoring updates.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

T = TypeVar("T")

MAX_WORKERS = 3
_EXECUTOR = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="long-task")


async def run_long_task(fn: Callable[..., T], /, *args, **kwargs) -> T:
    """Like ``asyncio.to_thread``, but in the long-task pool."""
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    return await loop.run_in_executor(_EXECUTOR, functools.partial(ctx.run, fn, *args, **kwargs))
