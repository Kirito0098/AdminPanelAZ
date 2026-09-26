"""Startup recovery fails only tasks whose worker is gone, not tasks of live workers."""

from __future__ import annotations

import subprocess
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import BackgroundTask
from app.services import background_tasks as bt
from app.services import process_identity as pi

DEAD_OWNER = "999999999:1"


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'tasks.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(bt, "SessionLocal", factory)
    yield factory
    engine.dispose()


@pytest.fixture()
def live_worker():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        yield pi.owner_of(child.pid)
    finally:
        child.kill()
        child.wait()


def _add(factory, task_id: str, status: str, owner: str | None) -> None:
    db = factory()
    try:
        db.add(BackgroundTask(id=task_id, task_type="run_doall", status=status, owner=owner))
        db.commit()
    finally:
        db.close()


def _status(factory, task_id: str) -> str:
    db = factory()
    try:
        return db.get(BackgroundTask, task_id).status
    finally:
        db.close()


def test_created_task_is_owned_by_current_process(session_factory):
    task_id = bt.background_task_service.create_queued_task("run_doall", "queued")
    db = session_factory()
    try:
        assert db.get(BackgroundTask, task_id).owner == pi.current_process_owner()
    finally:
        db.close()


def test_recovery_keeps_tasks_of_live_workers(session_factory, live_worker):
    _add(session_factory, "live-running", "running", live_worker)
    _add(session_factory, "live-queued", "queued", live_worker)
    _add(session_factory, "dead-running", "running", DEAD_OWNER)
    _add(session_factory, "legacy-running", "running", None)
    _add(session_factory, "dead-done", "completed", DEAD_OWNER)

    assert bt.background_task_service.recover_stale_running_tasks() == 2

    assert _status(session_factory, "live-running") == "running"
    assert _status(session_factory, "live-queued") == "queued"
    assert _status(session_factory, "dead-running") == "failed"
    assert _status(session_factory, "legacy-running") == "failed"
    assert _status(session_factory, "dead-done") == "completed"
