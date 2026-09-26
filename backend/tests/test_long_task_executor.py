"""Long scheduled jobs run in their own threads, apart from the default executor."""

from __future__ import annotations

import asyncio
import contextvars
import threading

import pytest

from app.services import long_task_executor


def test_runs_in_long_task_thread_and_returns_value():
    async def run():
        return await long_task_executor.run_long_task(lambda a, b=0: (threading.current_thread().name, a + b), 2, b=3)

    name, value = asyncio.run(run())
    assert name.startswith("long-task")
    assert value == 5


def test_exception_propagates():
    def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        asyncio.run(long_task_executor.run_long_task(boom))


def test_context_vars_are_copied_like_to_thread():
    var = contextvars.ContextVar("var", default="unset")

    async def run():
        var.set("request")
        return await long_task_executor.run_long_task(var.get)

    assert asyncio.run(run()) == "request"


def test_busy_long_tasks_do_not_block_default_executor():
    release = threading.Event()
    started = threading.Barrier(long_task_executor.MAX_WORKERS + 1)

    def hold():
        started.wait(2)
        release.wait(5)

    async def run():
        held = [
            asyncio.ensure_future(long_task_executor.run_long_task(hold))
            for _ in range(long_task_executor.MAX_WORKERS)
        ]
        await asyncio.to_thread(started.wait, 2)
        try:
            return await asyncio.wait_for(asyncio.to_thread(lambda: "monitoring"), 1)
        finally:
            release.set()
            await asyncio.gather(*held)

    assert asyncio.run(run()) == "monitoring"
