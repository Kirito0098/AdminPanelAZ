"""A locked SQLite write is retried after rollback, and the retried commit still carries the change."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import BackgroundTask
from app.services import background_tasks as bt

DEAD_OWNER = "999999999:1"


@pytest.fixture()
def factory(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'tasks.db'}",
        connect_args={"check_same_thread": False, "timeout": 0},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(bt, "SessionLocal", session_factory)
    yield session_factory
    engine.dispose()


@pytest.fixture()
def lock_until_first_retry(tmp_path, monkeypatch):
    """Hold the DB write lock until the first retry pause, like a concurrent writer would."""
    lockers: list[sqlite3.Connection] = []
    pauses: list[float] = []

    def lock() -> None:
        locker = sqlite3.connect(tmp_path / "tasks.db", isolation_level=None)
        locker.execute("BEGIN IMMEDIATE")
        lockers.append(locker)

    def release(seconds: float) -> None:
        pauses.append(seconds)
        for locker in lockers:
            if locker.in_transaction:
                locker.execute("ROLLBACK")

    monkeypatch.setattr(bt.time, "sleep", release)
    yield lock, pauses
    for locker in lockers:
        if locker.in_transaction:
            locker.execute("ROLLBACK")
        locker.close()


def _task(factory, task_id: str) -> BackgroundTask | None:
    db = factory()
    try:
        return db.get(BackgroundTask, task_id)
    finally:
        db.close()


def _add(factory, task_id: str, status: str, owner: str | None) -> None:
    db = factory()
    try:
        db.add(BackgroundTask(id=task_id, task_type="run_doall", status=status, owner=owner))
        db.commit()
    finally:
        db.close()


def test_update_survives_a_locked_first_commit(factory, lock_until_first_retry):
    lock, pauses = lock_until_first_retry
    _add(factory, "t1", "running", None)
    lock()

    bt.background_task_service.update_background_task("t1", progress_percent=42, message="half")

    assert len(pauses) == 1
    task = _task(factory, "t1")
    assert (task.progress_percent, task.message) == (42, "half")


def test_create_survives_a_locked_first_commit(factory, lock_until_first_retry):
    lock, pauses = lock_until_first_retry
    lock()

    task_id = bt.background_task_service.create_queued_task("run_doall", "queued")

    assert len(pauses) == 1
    assert _task(factory, task_id).status == "queued"


def test_recovery_survives_a_locked_first_commit(factory, lock_until_first_retry):
    lock, pauses = lock_until_first_retry
    _add(factory, "dead", "running", DEAD_OWNER)
    lock()

    assert bt.background_task_service.recover_stale_running_tasks() == 1

    assert len(pauses) == 1
    assert _task(factory, "dead").status == "failed"
