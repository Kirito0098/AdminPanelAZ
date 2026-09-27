"""Consume blocking iterators (agent SSE streams, subprocess output) from async code."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")

_DONE = object()


async def iterate_in_thread(iterable: Iterable[T]) -> AsyncIterator[T]:
    """Advance the iterator in a worker thread so waiting for the next item does not block the loop."""
    iterator = iter(iterable)
    # One thread per stream: close() must queue behind an in-flight next(), never run alongside it.
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="iterate-in-thread")
    loop = asyncio.get_running_loop()
    reading = False
    try:
        while True:
            reading = True
            item = await loop.run_in_executor(executor, next, iterator, _DONE)
            reading = False
            if item is _DONE:
                return
            yield item
    finally:
        close = getattr(iterator, "close", None)
        closing = executor.submit(close) if close is not None else None
        executor.shutdown(wait=False)
        # Cancelled mid-read: the pending next() may wait for the agent's next line; do not hold up cancellation.
        if closing is not None and not reading:
            await asyncio.wrap_future(closing)
