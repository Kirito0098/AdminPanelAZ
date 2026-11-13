"""One CIDR pipeline at a time, HA-primary only, and a stale runner must stop.

Concurrency is a critical node: two tabs used to start two ingests against the
same pool, a cron run could overlap a manual deploy, and a task marked failed by
the stale watchdog kept writing for minutes.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.routers import cidr_db
from app.services.cidr import cidr_tasks
from app.services.cidr.cidr_scheduler import run_nightly_cidr_pipeline
from app.services.node_sync import groups


@pytest.fixture(autouse=True)
def _memory_tasks(monkeypatch):
    """Drive the task bookkeeping without DB wiring; real code paths otherwise."""
    monkeypatch.setattr(cidr_tasks, "_USE_MEMORY", True)
    monkeypatch.setattr(cidr_tasks, "_CIDR_TASKS", {})
    for task_id in list(cidr_tasks._CANCEL_REQUESTED):
        cidr_tasks.clear_cancel(task_id)
    yield
    cidr_tasks._CIDR_TASKS.clear()


@pytest.fixture
def primary_only(monkeypatch):
    monkeypatch.setattr(cidr_db, "require_ha_primary_for_config_ops", lambda _db: None)


def _admin() -> SimpleNamespace:
    return SimpleNamespace(id=1, username="admin")


def _wait_terminal(task_id: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = cidr_tasks.get_cidr_task(task_id)
        if task and task.get("finished_at"):
            return task
        time.sleep(0.01)
    raise AssertionError("task did not reach a terminal state")


def test_mutating_route_rejects_other_active_task(primary_only):
    cidr_tasks.create_cidr_task("cidr_deploy", "deploy is running")

    with pytest.raises(HTTPException) as excinfo:
        cidr_db.cidr_db_generate(
            cidr_db.CidrDbGenerateRequest(action="generate"),
            _=_admin(),
            db=MagicMock(),
        )

    assert excinfo.value.status_code == 409
    assert "cidr_deploy" in str(excinfo.value.detail)


def test_same_task_type_still_answers_queued(primary_only):
    active_id = cidr_tasks.create_cidr_task("cidr_db_refresh", "refresh is running")

    response = cidr_db.cidr_db_refresh(
        cidr_db.CidrDbRefreshRequest(),
        user=_admin(),
        db=MagicMock(),
        cidr_db=MagicMock(),
    )

    assert response["queued"] is True
    assert response["task_id"] == active_id


@pytest.mark.parametrize(
    "task_type",
    ["cidr_db_refresh", "cidr_generate_from_db", "cidr_deploy", "antifilter_refresh"],
)
def test_clear_rejects_any_active_task(primary_only, task_type):
    cidr_tasks.create_cidr_task(task_type, "busy")

    with pytest.raises(HTTPException) as excinfo:
        cidr_db.cidr_db_clear(
            cidr_db.CidrDbClearRequest(),
            user=_admin(),
            db=MagicMock(),
            cidr_db=MagicMock(),
        )

    assert excinfo.value.status_code == 409


def test_cron_skips_when_pipeline_busy(monkeypatch):
    cidr_tasks.create_cidr_task("cidr_deploy", "manual deploy")
    ingest = MagicMock()
    monkeypatch.setattr("app.services.cidr.cidr_scheduler.run_ingest", ingest)

    summary = run_nightly_cidr_pipeline(MagicMock(), MagicMock())

    ingest.assert_not_called()
    assert summary["skipped"] == "active_task"
    assert summary["refresh"] is None


def test_stale_task_requests_cancel_and_runner_stops():
    task_id = cidr_tasks.create_cidr_task("cidr_db_refresh", "stale refresh")
    cidr_tasks.update_cidr_task(
        task_id,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    task = cidr_tasks.get_cidr_task(task_id)

    assert cidr_tasks.fail_stale_cidr_task(task, max_age_seconds=60) is True
    assert cidr_tasks.is_cancel_requested(task_id)

    reached_end = []

    def runner(progress_callback):
        progress_callback(5, "Провайдер 1/3: загрузка")
        reached_end.append("ran past the checkpoint")
        return {"success": True}

    cidr_tasks.start_cidr_task(task_id, runner)
    final = _wait_terminal(task_id)

    assert reached_end == []
    assert final["status"] == "failed"
    assert final["message"] == cidr_tasks.CIDR_TASK_CANCELLED_MESSAGE
    assert not cidr_tasks.is_cancel_requested(task_id)


def test_runner_stops_at_checkpoint_after_mid_run_cancel():
    task_id = cidr_tasks.create_cidr_task("cidr_db_refresh", "refresh")
    checkpoints = []

    def runner(progress_callback):
        progress_callback(5, "Файл 1/3")
        cidr_tasks.request_cancel(task_id)
        progress_callback(30, "Файл 2/3")
        checkpoints.append("leaked past the next checkpoint")
        return {"success": True}

    cidr_tasks.start_cidr_task(task_id, runner)
    final = _wait_terminal(task_id)

    assert checkpoints == []
    assert final["status"] == "failed"
    assert not cidr_tasks.is_cancel_requested(task_id)


def test_successful_run_clears_cancel_registry():
    task_id = cidr_tasks.create_cidr_task("cidr_generate_from_db", "compile")
    cidr_tasks.request_cancel("unrelated-task")

    cidr_tasks.start_cidr_task(task_id, lambda progress_callback: {"success": True})
    final = _wait_terminal(task_id)

    assert final["status"] == "completed"
    assert not cidr_tasks.is_cancel_requested(task_id)
    assert cidr_tasks.is_cancel_requested("unrelated-task")


def test_ha_replica_rejects_mutating_route(monkeypatch):
    replica = SimpleNamespace(id=2, name="replica-1")
    primary = SimpleNamespace(id=1, name="primary-1")
    group = SimpleNamespace(
        id=10,
        name="ha-group",
        primary_node_id=1,
        shared_domain="vpn.example.com",
        shared_domain_wireguard=None,
    )
    db = MagicMock()
    db.get.side_effect = lambda _model, node_id: {1: primary, 2: replica}.get(node_id)

    monkeypatch.setattr(
        "app.services.node_manager.get_active_node",
        lambda _db: replica,
    )
    monkeypatch.setattr(groups, "find_sync_group_containing_node", lambda _db, _id: (group, "replica"))

    with pytest.raises(HTTPException) as excinfo:
        cidr_db.cidr_db_clear(
            cidr_db.CidrDbClearRequest(),
            user=_admin(),
            db=db,
            cidr_db=MagicMock(),
        )

    assert excinfo.value.status_code == 403
    assert "replica" in str(excinfo.value.detail)
