"""CIDR schedule: an N-day interval runs every N days, not N+1."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services.cidr import cidr_scheduler as sched


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'panel.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(sched, "SessionLocal", factory)
    yield factory
    engine.dispose()


def test_last_run_is_pipeline_start(session_factory, monkeypatch):
    seen: dict[str, datetime] = {}

    def fake_pipeline(_db, _settings):
        seen["inside"] = datetime.now(timezone.utc)
        time.sleep(0.05)
        return {"refresh": {"status": "ok"}}

    monkeypatch.setattr(sched, "run_nightly_cidr_pipeline", fake_pipeline)

    sched._run_scheduled_refresh(SimpleNamespace(cidr_db_refresh_interval_days=14))

    db = session_factory()
    try:
        last = sched.get_last_cron_run_at(db)
    finally:
        db.close()
    assert last is not None
    assert last <= seen["inside"]


def test_interval_tolerates_run_stamped_seconds_after_the_slot(session_factory):
    db = session_factory()
    try:
        sched.mark_cron_run(db, datetime.now(timezone.utc) - timedelta(days=14) + timedelta(seconds=5))
        db.commit()
        assert sched._should_run_interval(db, 14) is True

        sched.mark_cron_run(db, datetime.now(timezone.utc) - timedelta(days=13))
        db.commit()
        assert sched._should_run_interval(db, 14) is False
    finally:
        db.close()


def test_next_run_is_n_days_after_a_run_that_started_past_the_slot():
    last = datetime(2026, 10, 1, 3, 0, 7, tzinfo=timezone.utc)
    now = datetime(2026, 10, 1, 3, 30, tzinfo=timezone.utc)

    next_run = sched.compute_next_run_at(
        enabled=True, hour=3, minute=0, interval_days=14, last_run=last, now=now
    )

    assert next_run == datetime(2026, 10, 15, 3, 0, tzinfo=timezone.utc)
