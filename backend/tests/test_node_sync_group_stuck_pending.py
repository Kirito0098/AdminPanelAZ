"""An HA group never stays ``pending`` after its sync task has ended."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import BackgroundTask, Node, NodeSyncGroup, SyncStatus
from app.services.node_sync import group_status, setup, shared_domain


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'panel.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr("app.database.SessionLocal", factory)
    return factory


def _group(factory, *, status=SyncStatus.pending, task_id: str | None = "t1", task_status: str | None = "running",
           task_error: str | None = None) -> int:
    with factory() as db:
        db.add(Node(id=1, name="primary", host="10.0.0.1"))
        if task_id and task_status:
            db.add(
                BackgroundTask(
                    id=task_id,
                    task_type="node_sync_setup",
                    status=task_status,
                    error=task_error,
                    created_at=datetime.now(timezone.utc),
                )
            )
        group = NodeSyncGroup(
            name="ha",
            shared_domain="vpn.example.com",
            primary_node_id=1,
            replica_node_ids="[2]",
            sync_status=status,
            last_sync_task_id=task_id,
        )
        db.add(group)
        db.commit()
        return group.id


def _read(factory, group_id):
    with factory() as db:
        group = db.get(NodeSyncGroup, group_id)
        return group.sync_status, group.last_sync_error


def test_setup_task_failure_marks_group_failed(sessions):
    group_id = _group(sessions)

    def boom(*_a, **_k):
        raise RuntimeError("Push full прерван: проблемы связи. replica: node_unreachable — offline")

    with patch.object(setup, "apply_shared_domain_to_members", return_value={"success": True}), patch.object(
        setup, "run_push_full", side_effect=boom
    ):
        with pytest.raises(RuntimeError):
            setup.make_group_setup_callable(group_id)()

    status, error = _read(sessions, group_id)
    assert status == SyncStatus.failed
    assert "node_unreachable" in error


def test_setup_task_failure_in_shared_domain_step_marks_group_failed(sessions):
    group_id = _group(sessions)
    with patch.object(setup, "apply_shared_domain_to_members", side_effect=OSError("ssh timeout")):
        with pytest.raises(OSError):
            setup.make_group_setup_callable(group_id)()
    status, error = _read(sessions, group_id)
    assert status == SyncStatus.failed
    assert "ssh timeout" in error


def test_setup_failure_after_uncommitted_changes_still_marks_group_failed(sessions):
    group_id = _group(sessions)

    def dirty_then_fail(db, group, **_kwargs):
        group.name = "half-written"
        db.flush()
        raise RuntimeError("agent 500")

    with patch.object(setup, "apply_shared_domain_to_members", return_value={"success": True}), patch.object(
        setup, "run_push_full", side_effect=dirty_then_fail
    ):
        with pytest.raises(RuntimeError):
            setup.make_group_setup_callable(group_id)()

    with sessions() as db:
        group = db.get(NodeSyncGroup, group_id)
        assert group.sync_status == SyncStatus.failed
        assert group.name == "ha", "the failed step's half-written changes are rolled back"


def test_shared_domain_task_failure_marks_group_failed(sessions):
    group_id = _group(sessions)
    with patch.object(shared_domain, "apply_shared_domain_to_members", side_effect=RuntimeError("doall.sh failed")):
        with pytest.raises(RuntimeError):
            shared_domain.make_shared_domain_callable(group_id)()
    status, error = _read(sessions, group_id)
    assert status == SyncStatus.failed
    assert "doall.sh failed" in error


@pytest.mark.parametrize(
    ("task_status", "task_id", "expected"),
    [
        pytest.param("running", "t1", SyncStatus.pending, id="running"),
        pytest.param("queued", "t1", SyncStatus.pending, id="queued"),
        pytest.param("failed", "t1", SyncStatus.failed, id="task-failed"),
        pytest.param("completed", "t1", SyncStatus.failed, id="task-completed"),
        pytest.param(None, "gone", SyncStatus.failed, id="task-missing"),
        pytest.param(None, None, SyncStatus.failed, id="no-task-id"),
    ],
)
def test_recover_stuck_pending_groups(sessions, task_status, task_id, expected):
    group_id = _group(sessions, task_id=task_id, task_status=task_status, task_error="Задача прервана перезапуском панели")
    with sessions() as db:
        recovered = group_status.recover_stuck_pending_groups(db)
    status, error = _read(sessions, group_id)
    assert status == expected
    assert recovered == (1 if expected == SyncStatus.failed else 0)
    if expected == SyncStatus.failed:
        assert error


def test_recovered_group_keeps_task_error(sessions):
    group_id = _group(sessions, task_status="failed", task_error="Задача прервана перезапуском панели")
    with sessions() as db:
        group_status.recover_stuck_pending_groups(db)
    assert "прервана перезапуском" in _read(sessions, group_id)[1]


def test_recover_leaves_other_statuses(sessions):
    group_id = _group(sessions, status=SyncStatus.synced, task_status="failed")
    with sessions() as db:
        assert group_status.recover_stuck_pending_groups(db) == 0
    assert _read(sessions, group_id) == (SyncStatus.synced, None)


def test_leader_startup_recovers_groups_after_stale_tasks(sessions, monkeypatch):
    from app import main

    order: list[str] = []
    monkeypatch.setattr(
        "app.services.background_tasks.background_task_service.recover_stale_running_tasks",
        lambda: order.append("tasks") or 0,
    )
    monkeypatch.setattr(
        "app.services.node_sync.group_status.recover_stuck_pending_groups_once",
        lambda: order.append("groups") or 0,
    )
    monkeypatch.setattr("app.services.server_reboot.interrupt_abandoned_reboots", lambda: 0)
    monkeypatch.setattr("app.services.cidr.pipeline.list_migration.migrate_legacy_cidr_list_dir", lambda: 0)
    monkeypatch.setattr("app.services.systemd_refresh.migrate_stale_systemd_units_on_startup", lambda *a, **k: None)
    monkeypatch.setattr(main.ip_restriction_service, "sync_firewall", lambda: order.append("firewall"))
    monkeypatch.setattr(main.ip_restriction_service, "sync_whitelist_port_firewall", lambda _db: None)
    main.run_leader_startup_actions()
    assert order[:2] == ["tasks", "groups"]


def test_reconcile_pass_recovers_stuck_groups_first(sessions, monkeypatch):
    from app.services.node_sync import reconcile_worker

    group_id = _group(sessions, task_status="failed", task_error="boom")
    monkeypatch.setattr(reconcile_worker, "SessionLocal", sessions)
    verified: list[int] = []
    monkeypatch.setattr(
        reconcile_worker, "verify_sync_group", lambda db, group: verified.append(group.id) or {"ready": True}
    )
    reconcile_worker.reconcile_sync_groups_once()
    assert _read(sessions, group_id)[0] == SyncStatus.failed
    assert verified == [group_id]
