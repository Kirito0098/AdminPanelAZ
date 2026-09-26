# backend/tests/test_server_reboot.py
import logging
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ServerRebootRecord
from app.services import process_identity as pi
from app.services import server_reboot as sr

DEAD_OWNER = "999999999:1"


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'reboot.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(sr, "SessionLocal", sessionmaker(bind=engine))
    sr.clear_all_for_tests()
    yield
    sr.clear_all_for_tests()
    engine.dispose()


@pytest.fixture()
def live_worker():
    """Owner token of another worker process that is still running."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        yield pi.owner_of(child.pid)
    finally:
        child.kill()
        child.wait()


@contextmanager
def _other_worker(monkeypatch):
    """Requests routed to a worker that did not schedule the reboot."""
    with monkeypatch.context() as m:
        m.setattr(sr, "_timers", {})
        m.setattr(sr, "_execute_fns", {})
        yield


def test_cancel_from_other_worker_prevents_reboot(monkeypatch):
    executed = Mock()
    pending = sr.schedule_reboot(
        node_id=7, node_name="n7", scheduled_by="admin", execute_fn=executed, delay_seconds=0.2
    )
    with _other_worker(monkeypatch):
        assert [p.reboot_id for p in sr.list_pending()] == [pending.reboot_id]
        assert sr.cancel_reboot(pending.reboot_id).status == "cancelled"
    time.sleep(0.35)
    executed.assert_not_called()
    assert sr.get_pending(pending.reboot_id).status == "cancelled"


def test_duplicate_is_detected_across_workers(monkeypatch):
    sr.schedule_reboot(node_id=8, node_name="n8", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    with _other_worker(monkeypatch):
        with pytest.raises(sr.RebootError) as ei:
            sr.schedule_reboot(node_id=8, node_name="n8", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    assert ei.value.code == "duplicate_pending"


def test_times_are_utc_aware():
    pending = sr.schedule_reboot(node_id=9, node_name="n9", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    stored = sr.get_pending(pending.reboot_id)
    assert stored.execute_at.utcoffset() == timedelta(0)
    assert abs((stored.execute_at - pending.execute_at).total_seconds()) < 1


def _insert_row(*, node_id: int, status: str, execute_at: datetime, owner: str | None = DEAD_OWNER) -> str:
    db = sr.SessionLocal()
    try:
        row = ServerRebootRecord(
            id=f"stale-{node_id}-{status}",
            node_id=node_id,
            node_name=f"n{node_id}",
            scheduled_by="a",
            created_at=execute_at - timedelta(seconds=15),
            execute_at=execute_at,
            status=status,
            owner=owner,
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def test_scheduled_reboot_is_owned_by_current_process():
    pending = sr.schedule_reboot(node_id=14, node_name="n14", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    db = sr.SessionLocal()
    try:
        assert db.get(ServerRebootRecord, pending.reboot_id).owner == pi.current_process_owner()
    finally:
        db.close()


def test_reboot_of_dead_worker_does_not_block_new_one():
    """Worker that scheduled it died before the timer fired."""
    stale_id = _insert_row(node_id=10, status="pending", execute_at=datetime.utcnow() + timedelta(seconds=10))
    fresh = sr.schedule_reboot(node_id=10, node_name="n10", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    assert fresh.status == "pending"
    assert sr.get_pending(stale_id).status == "interrupted"
    assert [p.reboot_id for p in sr.list_pending()] == [fresh.reboot_id]


def test_overdue_reboot_of_live_worker_does_not_block_new_one(live_worker):
    """The worker is alive but its timer never ran the reboot."""
    stale_id = _insert_row(
        node_id=15,
        status="pending",
        execute_at=datetime.utcnow() - sr.ABANDONED_AFTER - timedelta(seconds=1),
        owner=live_worker,
    )
    sr.schedule_reboot(node_id=15, node_name="n15", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    assert sr.get_pending(stale_id).status == "interrupted"


def test_listing_hides_abandoned_reboots_without_writing(live_worker):
    dead_id = _insert_row(node_id=13, status="pending", execute_at=datetime.utcnow() + timedelta(seconds=10))
    overdue_id = _insert_row(
        node_id=16,
        status="pending",
        execute_at=datetime.utcnow() - sr.ABANDONED_AFTER - timedelta(seconds=1),
        owner=live_worker,
    )
    assert sr.list_pending() == []
    assert sr.get_pending(dead_id).status == "pending"
    assert sr.get_pending(overdue_id).status == "pending"


def test_pending_reboot_of_live_worker_is_listed(live_worker):
    live_id = _insert_row(
        node_id=17, status="pending", execute_at=datetime.utcnow() + timedelta(seconds=10), owner=live_worker
    )
    assert [p.reboot_id for p in sr.list_pending()] == [live_id]


def test_long_running_reboot_of_live_worker_keeps_its_status(live_worker):
    """The reboot callback may run for minutes; its final status must not be overwritten."""
    executing_id = _insert_row(
        node_id=18,
        status="executing",
        execute_at=datetime.utcnow() - sr.ABANDONED_AFTER - timedelta(minutes=5),
        owner=live_worker,
    )
    sr.schedule_reboot(node_id=19, node_name="n19", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    assert sr.interrupt_abandoned_reboots() == 0
    assert sr.get_pending(executing_id).status == "executing"


def test_startup_interrupts_only_reboots_of_dead_workers(live_worker):
    """A worker restarted by uvicorn must not cancel reboots scheduled by the workers still running."""
    pending_id = _insert_row(node_id=11, status="pending", execute_at=datetime.utcnow() + timedelta(seconds=10))
    executing_id = _insert_row(node_id=12, status="executing", execute_at=datetime.utcnow())
    legacy_id = _insert_row(
        node_id=20, status="pending", execute_at=datetime.utcnow() + timedelta(seconds=10), owner=None
    )
    live_id = _insert_row(
        node_id=21, status="pending", execute_at=datetime.utcnow() + timedelta(seconds=10), owner=live_worker
    )

    assert sr.interrupt_abandoned_reboots() == 3

    assert sr.get_pending(pending_id).status == "interrupted"
    assert sr.get_pending(executing_id).status == "interrupted"
    assert sr.get_pending(legacy_id).status == "interrupted"
    assert sr.get_pending(live_id).status == "pending"
    sr.schedule_reboot(node_id=12, node_name="n12", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)


def test_timer_errors_are_logged(monkeypatch, caplog):
    def locked(*_args, **_kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(sr, "_set_status", locked)
    with caplog.at_level(logging.ERROR, logger=sr.logger.name):
        sr.schedule_reboot(node_id=22, node_name="n22", scheduled_by="a", execute_fn=Mock(), delay_seconds=0.02)
        time.sleep(0.15)
    assert any("n22" in record.getMessage() for record in caplog.records)


def test_schedule_requires_exact_confirm_via_wrapper():
    # schedule_reboot itself does not take confirm — API will validate.
    # Here: schedule creates pending and calls execute_fn after delay.
    executed = Mock()
    pending = sr.schedule_reboot(
        node_id=1,
        node_name="local",
        scheduled_by="admin",
        execute_fn=executed,
        delay_seconds=0.05,
    )
    assert pending.status == "pending"
    assert pending.node_id == 1
    time.sleep(0.12)
    executed.assert_called_once()
    assert executed.call_args[0][0].reboot_id == pending.reboot_id
    assert sr.get_pending(pending.reboot_id).status == "executed"


def test_cancel_before_execute():
    executed = Mock()
    pending = sr.schedule_reboot(
        node_id=2,
        node_name="n2",
        scheduled_by="admin",
        execute_fn=executed,
        delay_seconds=1.0,
    )
    cancelled = sr.cancel_reboot(pending.reboot_id)
    assert cancelled.status == "cancelled"
    time.sleep(0.15)
    executed.assert_not_called()


def test_duplicate_pending_same_node_raises():
    sr.schedule_reboot(node_id=3, node_name="n3", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    with pytest.raises(sr.RebootError) as ei:
        sr.schedule_reboot(node_id=3, node_name="n3", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    assert ei.value.code == "duplicate_pending"


def test_cancel_unknown_raises():
    with pytest.raises(sr.RebootError) as ei:
        sr.cancel_reboot("missing")
    assert ei.value.code == "not_found"


def test_list_pending_only_active():
    p = sr.schedule_reboot(node_id=4, node_name="n4", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    assert [x.reboot_id for x in sr.list_pending()] == [p.reboot_id]
    sr.cancel_reboot(p.reboot_id)
    assert sr.list_pending() == []


def test_execute_failure_marks_failed():
    def boom(_p):
        raise RuntimeError("nope")

    pending = sr.schedule_reboot(
        node_id=5,
        node_name="n5",
        scheduled_by="a",
        execute_fn=boom,
        delay_seconds=0.05,
    )
    time.sleep(0.12)
    assert sr.get_pending(pending.reboot_id).status == "failed"


def test_cancel_during_execute_is_not_cancellable():
    started = threading.Event()
    release = threading.Event()

    def slow(_p):
        started.set()
        release.wait(2)

    pending = sr.schedule_reboot(
        node_id=6,
        node_name="n6",
        scheduled_by="a",
        execute_fn=slow,
        delay_seconds=0.05,
    )
    assert started.wait(1)
    with pytest.raises(sr.RebootError) as ei:
        sr.cancel_reboot(pending.reboot_id)
    assert ei.value.code == "not_cancellable"
    release.set()
    time.sleep(0.05)
    assert sr.get_pending(pending.reboot_id).status == "executed"


def _hold_set_status(monkeypatch, *, hold_when, until: threading.Event):
    """Delay the pending→X status switch matched by ``hold_when(new)`` until ``until`` is set."""
    real = sr._set_status

    def wrapped(reboot_id, *, expected, new):
        if expected == "pending" and hold_when(new):
            assert until.wait(2), "the other side never ran"
        return real(reboot_id, expected=expected, new=new)

    monkeypatch.setattr(sr, "_set_status", wrapped)


def test_cancel_wins_when_timer_fired_but_not_switched_yet(monkeypatch):
    cancelled = threading.Event()
    _hold_set_status(monkeypatch, hold_when=lambda new: new == "executing", until=cancelled)
    executed = Mock()
    pending = sr.schedule_reboot(
        node_id=8, node_name="n8", scheduled_by="a", execute_fn=executed, delay_seconds=0
    )
    timer = sr._timers.get(pending.reboot_id)

    result = sr.cancel_reboot(pending.reboot_id)
    cancelled.set()
    if timer is not None:
        timer.join(2)
    time.sleep(0.05)

    assert result.status == "cancelled"
    executed.assert_not_called()
    assert sr.get_pending(pending.reboot_id).status == "cancelled"


def test_timer_wins_when_cancel_checked_before_switch(monkeypatch):
    ran = threading.Event()
    _hold_set_status(monkeypatch, hold_when=lambda new: new == "cancelled", until=ran)
    calls = []

    def execute(p):
        calls.append(p.status)
        ran.set()

    pending = sr.schedule_reboot(
        node_id=9, node_name="n9", scheduled_by="a", execute_fn=execute, delay_seconds=0.05
    )

    with pytest.raises(sr.RebootError) as ei:
        sr.cancel_reboot(pending.reboot_id)
    time.sleep(0.05)

    assert ei.value.code == "not_cancellable"
    assert calls == ["executing"]
    assert sr.get_pending(pending.reboot_id).status == "executed"


def test_simultaneous_timer_and_cancel_have_exactly_one_winner():
    for node_id in range(100, 130):
        calls = []
        pending = sr.schedule_reboot(
            node_id=node_id,
            node_name=f"n{node_id}",
            scheduled_by="a",
            execute_fn=lambda p: calls.append(p.reboot_id),
            delay_seconds=0,
        )
        try:
            sr.cancel_reboot(pending.reboot_id)
            cancelled = True
        except sr.RebootError as exc:
            assert exc.code == "not_cancellable"
            cancelled = False
        deadline = time.monotonic() + 2
        while sr.get_pending(pending.reboot_id).status in sr.ACTIVE_STATUSES and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.02)
        status = sr.get_pending(pending.reboot_id).status
        if cancelled:
            assert (status, calls) == ("cancelled", [])
        else:
            assert (status, calls) == ("executed", [pending.reboot_id])
