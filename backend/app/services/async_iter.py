"""Consume blocking iterators (agent SSE streams, subprocess output) from async code."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import TypeVar

T = TypeVar("T")

_DONE = object()


async def iterate_in_thread(iterable: Iterable[T]) -> AsyncIterator[T]:
    """Advance the iterator in a worker thread so waiting for the next item does not block the loop."""
    iterator = iter(iterable)
    try:
        while True:
            item = await asyncio.to_thread(next, iterator, _DONE)
            if item is _DONE:
                return
            yield item
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            await asyncio.to_thread(close)
