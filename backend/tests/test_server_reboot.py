# backend/tests/test_server_reboot.py
import threading
import time
from unittest.mock import Mock

import pytest

from app.services import server_reboot as sr


@pytest.fixture(autouse=True)
def _clean():
    sr.clear_all_for_tests()
    yield
    sr.clear_all_for_tests()


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
