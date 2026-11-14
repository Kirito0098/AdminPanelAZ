"""One heavy apply at a time: enqueue-time 409 plus the runtime apply slot.

Two doall.sh runs on one node raced for ``config/``, ``result/`` and iptables:
the enqueue guards only knew their own task type, so ``routing_apply``,
``run_doall``, ``config_apply`` and ``recreate_profiles`` could overlap. These
tests pin both layers: the task-type guard in the routers and the per-node
``apply_slot`` that never waits.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.routers import cidr_db, maintenance, routing, settings
from app.services import background_tasks as background_tasks_module
from app.services.background_tasks import (
    HEAVY_APPLY_TASK_TYPES,
    find_active_heavy_apply_task,
)
from app.services.cidr import apply_pipeline

background_task_service = background_tasks_module.background_task_service


def _admin() -> SimpleNamespace:
    return SimpleNamespace(id=1, username="admin")


def _heavy_task(task_type: str = "run_doall", subject_key: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"task-{task_type}",
        task_type=task_type,
        status="running",
        subject_key=subject_key,
    )


def _db_with_tasks(*tasks: SimpleNamespace) -> MagicMock:
    """Session stub: the heavy-apply query returns ``tasks``, newest first."""
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = list(tasks)
    return db


@pytest.fixture
def config_ops_allowed(monkeypatch):
    monkeypatch.setattr(routing, "require_ha_primary_for_config_ops", lambda _db: None)
    monkeypatch.setattr(settings, "require_ha_primary_for_config_ops", lambda _db: None)
    monkeypatch.setattr(cidr_db, "require_ha_primary_for_config_ops", lambda _db: None)
    # The per-type guard is a live DB lookup: no row means "nothing running".
    monkeypatch.setattr(background_task_service, "find_active_task", lambda *_a, **_k: None)


# --- apply_slot -------------------------------------------------------------


def _apply_in_thread(entered: threading.Event, release: threading.Event, box: dict) -> None:
    with apply_pipeline.apply_slot():
        entered.set()
        release.wait(5)
    box["done"] = True


def test_apply_slot_rejects_second_apply_immediately():
    assert not apply_pipeline.is_apply_busy()

    entered = threading.Event()
    release = threading.Event()
    box: dict = {}
    holder = threading.Thread(
        target=_apply_in_thread, args=(entered, release, box), daemon=True
    )
    holder.start()
    try:
        assert entered.wait(5)
        assert apply_pipeline.is_apply_busy()
        with pytest.raises(HTTPException) as excinfo:
            with apply_pipeline.apply_slot():
                pass
        assert excinfo.value.status_code == 409
        assert "уже выполняется" in str(excinfo.value.detail)
    finally:
        release.set()
        holder.join(5)

    assert box["done"] is True
    assert not apply_pipeline.is_apply_busy()
    # Released: the next apply enters.
    with apply_pipeline.apply_slot():
        assert apply_pipeline.is_apply_busy()


def test_apply_slot_is_reentrant_for_nested_task_steps():
    # One task nests applies (doall → HA replicate → replica doall): same thread keeps the slot.
    with apply_pipeline.apply_slot():
        with apply_pipeline.apply_slot():
            assert apply_pipeline.is_apply_busy()
    assert not apply_pipeline.is_apply_busy()


def test_apply_slot_releases_on_exception():
    with pytest.raises(ValueError):
        with apply_pipeline.apply_slot():
            raise ValueError("doall.sh упал")

    assert not apply_pipeline.is_apply_busy()
    with apply_pipeline.apply_slot():
        pass


def test_apply_slot_is_per_node():
    first = apply_pipeline.apply_key_for_adapter(MagicMock(base_url="https://10.0.0.1:8443"))
    second = apply_pipeline.apply_key_for_adapter(MagicMock(base_url="https://10.0.0.2:8443"))

    assert first != second
    with apply_pipeline.apply_slot(node_key=first):
        # A replica is another host: it may apply while the primary does.
        with apply_pipeline.apply_slot(node_key=second):
            pass


# --- enqueue-time guard -----------------------------------------------------


def test_heavy_types_cover_every_apply_entry_point():
    assert HEAVY_APPLY_TASK_TYPES == {
        "run_doall",
        "routing_apply",
        "routing_apply_replica",
        "config_apply",
        "recreate_profiles",
    }


def test_find_active_heavy_apply_task_scopes_by_node():
    db = _db_with_tasks(
        _heavy_task("config_apply", subject_key="node:2:config-apply"),
    )

    assert find_active_heavy_apply_task(db, node_id=2) is not None
    assert find_active_heavy_apply_task(db, node_id=1) is None

    # A task without a node in its subject key may act on any node.
    unscoped = _db_with_tasks(_heavy_task("run_doall"))
    assert find_active_heavy_apply_task(unscoped, node_id=1) is not None


def test_routing_apply_rejected_while_run_doall_runs(config_ops_allowed):
    db = _db_with_tasks(_heavy_task("run_doall"))

    with pytest.raises(HTTPException) as excinfo:
        routing.apply_routing(admin=_admin(), db=db)

    assert excinfo.value.status_code == 409
    assert "run_doall" in str(excinfo.value.detail)


def test_run_doall_rejected_while_routing_apply_runs(config_ops_allowed):
    db = _db_with_tasks(_heavy_task("routing_apply"))

    with pytest.raises(HTTPException) as excinfo:
        maintenance.run_doall(request=None, db=db, admin=_admin())

    assert excinfo.value.status_code == 409
    assert "routing_apply" in str(excinfo.value.detail)


def test_recreate_profiles_rejected_while_apply_runs(config_ops_allowed):
    db = _db_with_tasks(_heavy_task("run_doall"))

    with pytest.raises(HTTPException) as excinfo:
        settings.recreate_profiles(request=None, db=db, admin=_admin())

    assert excinfo.value.status_code == 409


def test_run_doall_passes_when_no_heavy_apply(monkeypatch, config_ops_allowed):
    db = _db_with_tasks()
    enqueued: list[str] = []

    def fake_enqueue(task_type, _callable, **_kwargs):
        enqueued.append(task_type)
        return SimpleNamespace(id="new-task")

    monkeypatch.setattr(background_task_service, "enqueue_background_task", fake_enqueue)
    monkeypatch.setattr(
        background_task_service, "build_accepted_payload", lambda *_a, **_k: {"success": True}
    )

    result = maintenance.run_doall(request=None, db=db, admin=_admin())

    assert enqueued == ["run_doall"]
    assert result == {"success": True}


def test_generate_with_apply_after_rejected_while_apply_runs(config_ops_allowed):
    db = _db_with_tasks(_heavy_task("run_doall"))

    with pytest.raises(HTTPException) as excinfo:
        cidr_db.cidr_db_generate(
            cidr_db.CidrDbGenerateRequest(action="generate", apply_after=True),
            _=_admin(),
            db=db,
        )

    assert excinfo.value.status_code == 409
    assert "run_doall" in str(excinfo.value.detail)


# --- the tasks themselves ---------------------------------------------------


def test_routing_apply_and_run_doall_never_overlap():
    started = threading.Event()
    release = threading.Event()
    adapter = MagicMock()

    def _slow_sync() -> dict:
        started.set()
        release.wait(5)
        return {"restored": []}

    adapter.sync_cidr_providers.side_effect = _slow_sync
    adapter.apply_config_changes.return_value = "doall ok"
    box: dict = {}

    def _first() -> None:
        try:
            box["result"] = background_task_service.task_routing_apply(
                adapter, recreate_profiles=False
            )
        except Exception as exc:  # surfaced by the assertions below
            box["error"] = exc

    worker = threading.Thread(target=_first, daemon=True)
    worker.start()
    try:
        assert started.wait(5), "routing apply did not start"
        assert apply_pipeline.is_apply_busy()

        with pytest.raises(RuntimeError, match="Применение конфигурации уже выполняется"):
            background_task_service.task_run_doall(MagicMock(), recreate_profiles=False)
    finally:
        release.set()
        worker.join(5)

    assert "error" not in box
    assert "doall ok" in box["result"]["output"]
    assert not apply_pipeline.is_apply_busy()
