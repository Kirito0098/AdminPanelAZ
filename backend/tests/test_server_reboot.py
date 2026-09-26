# backend/tests/test_server_reboot.py
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ServerRebootRequest
from app.services import server_reboot as sr


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'reboot.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(sr, "SessionLocal", sessionmaker(bind=engine))
    sr.clear_all_for_tests()
    yield
    sr.clear_all_for_tests()
    engine.dispose()


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


def _insert_row(*, node_id: int, status: str, execute_at: datetime) -> str:
    db = sr.SessionLocal()
    try:
        row = ServerRebootRequest(
            id=f"stale-{node_id}-{status}",
            node_id=node_id,
            node_name=f"n{node_id}",
            scheduled_by="a",
            created_at=execute_at - timedelta(seconds=15),
            execute_at=execute_at,
            status=status,
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def test_abandoned_reboot_does_not_block_new_one():
    """Worker that scheduled it died before the timer fired."""
    stale_id = _insert_row(
        node_id=10, status="pending", execute_at=datetime.utcnow() - sr.ABANDONED_AFTER - timedelta(seconds=1)
    )
    fresh = sr.schedule_reboot(node_id=10, node_name="n10", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    assert fresh.status == "pending"
    assert sr.get_pending(stale_id).status == "interrupted"
    assert [p.reboot_id for p in sr.list_pending()] == [fresh.reboot_id]


def test_startup_interrupts_reboots_of_previous_process():
    pending_id = _insert_row(node_id=11, status="pending", execute_at=datetime.utcnow() + timedelta(seconds=10))
    executing_id = _insert_row(node_id=12, status="executing", execute_at=datetime.utcnow())

    assert sr.interrupt_reboots_of_previous_process() == 2

    assert sr.get_pending(pending_id).status == "interrupted"
    assert sr.get_pending(executing_id).status == "interrupted"
    sr.schedule_reboot(node_id=12, node_name="n12", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)


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
