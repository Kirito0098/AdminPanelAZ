"""Only one uvicorn worker runs schedulers and one-shot startup actions."""

from __future__ import annotations

import asyncio
import stat
from pathlib import Path
from types import SimpleNamespace

from app.services import lifespan_workers
from app.services.worker_leader import WorkerLeaderLock


def test_lock_is_exclusive_between_workers(tmp_path: Path):
    path = tmp_path / "adminpanel.db.leader.lock"
    first = WorkerLeaderLock(path)
    second = WorkerLeaderLock(path)

    assert first.try_acquire() is True
    assert second.try_acquire() is False
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    first.release()
    assert second.try_acquire() is True
    second.release()


def test_leader_starts_workers_and_startup_actions(tmp_path: Path):
    lock = WorkerLeaderLock(tmp_path / "leader.lock")
    calls: list[str] = []

    async def scenario():
        tasks = lifespan_workers.start_leader_workers(
            lock,
            start=lambda: calls.append("start") or {},
            on_startup=lambda: calls.append("startup"),
        )
        await lifespan_workers.cancel_background_tasks(tasks)

    asyncio.run(scenario())
    lock.release()
    assert calls == ["start", "startup"]


def test_follower_takes_over_when_leader_exits(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(lifespan_workers, "LEADER_RETRY_SECONDS", 0.01)
    path = tmp_path / "leader.lock"
    leader = WorkerLeaderLock(path)
    assert leader.try_acquire()
    follower = WorkerLeaderLock(path)
    calls: list[str] = []

    async def scenario():
        worker_cancelled = asyncio.Event()

        async def worker():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                worker_cancelled.set()
                raise

        def start():
            calls.append("start")
            return {"worker": asyncio.create_task(worker())}

        tasks = lifespan_workers.start_leader_workers(
            follower,
            start=start,
            on_startup=lambda: calls.append("startup"),
        )
        await asyncio.sleep(0.05)
        assert calls == []

        leader.release()
        for _ in range(100):
            if calls:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0)
        assert "worker" in tasks

        await lifespan_workers.cancel_background_tasks(tasks)
        return worker_cancelled.is_set()

    worker_was_cancelled = asyncio.run(scenario())
    follower.release()
    assert calls == ["start"]
    assert worker_was_cancelled


def test_lifespan_skips_workers_while_another_worker_leads(tmp_path: Path, monkeypatch):
    from app import main

    db_path = tmp_path / "adminpanel.db"
    holder = WorkerLeaderLock(lifespan_workers.leader_lock_path(db_path))
    assert holder.try_acquire()
    calls: list[str] = []

    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(database_url=f"sqlite:///{db_path}", backup_root=tmp_path / "backups"),
    )
    monkeypatch.setattr(main, "seed_database", lambda: None)
    monkeypatch.setattr(main, "restrict_sensitive_file_permissions", lambda _paths: None)
    monkeypatch.setattr(main, "spawn_background_tasks", lambda **_kw: calls.append("spawn") or {})
    monkeypatch.setattr(main, "run_leader_startup_actions", lambda: calls.append("startup"))
    monkeypatch.setattr(main, "should_start_resource_monitor", lambda: False)

    async def scenario():
        async with main.lifespan(main.app):
            await asyncio.sleep(0)

    asyncio.run(scenario())
    assert calls == []

    holder.release()
    asyncio.run(scenario())
    assert calls == ["spawn", "startup"]
    assert holder.try_acquire(), "shutdown must hand leadership to the remaining workers"
    holder.release()


def test_failed_takeover_is_logged_and_frees_the_lock(tmp_path: Path, monkeypatch, caplog):
    monkeypatch.setattr(lifespan_workers, "LEADER_RETRY_SECONDS", 0.01)
    path = tmp_path / "leader.lock"
    leader = WorkerLeaderLock(path)
    assert leader.try_acquire()
    follower = WorkerLeaderLock(path)

    def broken_start():
        raise RuntimeError("scheduler import failed")

    async def scenario():
        tasks = lifespan_workers.start_leader_workers(follower, start=broken_start, on_startup=lambda: None)
        leader.release()
        await asyncio.wait_for(tasks["leader_takeover"], 1)

    with caplog.at_level("ERROR", logger=lifespan_workers.logger.name):
        asyncio.run(scenario())
    assert any("take over" in r.getMessage() for r in caplog.records)
    other = WorkerLeaderLock(path)
    assert other.try_acquire(), "another worker must be able to run the schedulers"
    other.release()


def test_cancel_continues_past_a_failing_task(caplog):
    cancelled: list[str] = []

    async def failing():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise RuntimeError("cleanup failed") from None

    async def healthy():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append("healthy")
            raise

    async def scenario():
        tasks = {"failing": asyncio.create_task(failing()), "healthy": asyncio.create_task(healthy())}
        await asyncio.sleep(0)
        await lifespan_workers.cancel_background_tasks(tasks)

    with caplog.at_level("ERROR", logger=lifespan_workers.logger.name):
        asyncio.run(scenario())
    assert cancelled == ["healthy"]
    assert any("failing" in r.getMessage() for r in caplog.records)
