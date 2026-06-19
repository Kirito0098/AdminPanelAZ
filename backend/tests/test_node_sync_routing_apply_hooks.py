"""Integration tests for HA routing apply orchestration (step C.3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import AppSetting, BackgroundTask, Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.background_tasks import background_task_service
from app.services.node_sync.groups import serialize_replica_node_ids


def _set_active_node(session_factory, node_id: int) -> None:
    db = session_factory()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == "active_node_id").first()
        if row:
            row.value = str(node_id)
        else:
            db.add(AppSetting(key="active_node_id", value=str(node_id)))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def ha_routing_apply_env(api_test_env):
    session_factory = api_test_env["session_factory"]
    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica1 = Node(name="replica-a", host="10.0.0.41", port=9100, status=NodeStatus.online)
    replica2 = Node(name="replica-b", host="10.0.0.42", port=9100, status=NodeStatus.online)
    db.add_all([replica1, replica2])
    db.commit()
    db.refresh(replica1)
    db.refresh(replica2)

    group = NodeSyncGroup(
        name="HA routing",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica1.id, replica2.id]),
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    db.add(group)
    db.commit()

    primary_id = primary.id
    replica_ids = [replica1.id, replica2.id]
    db.close()

    _set_active_node(session_factory, primary_id)
    yield {
        **api_test_env,
        "primary_id": primary_id,
        "replica_ids": replica_ids,
    }


def test_routing_apply_ha_enqueues_primary_and_replica_tasks(ha_routing_apply_env):
    client = TestClient(ha_routing_apply_env["app"])
    primary_adapter = MagicMock()
    enqueued: list[tuple[str, str | None]] = []
    task_counter = {"n": 0}

    def fake_enqueue(task_type, task_callable, *, created_by_username=None, queued_message=None):
        task_counter["n"] += 1
        enqueued.append((task_type, queued_message))
        return BackgroundTask(
            id=f"task-{task_counter['n']}",
            task_type=task_type,
            status="queued",
            message=queued_message,
        )

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch(
            "app.routers.routing.get_active_node",
            side_effect=lambda db: db.query(Node).filter_by(id=ha_routing_apply_env["primary_id"]).one(),
        ),
        patch.object(background_task_service, "enqueue_background_task", side_effect=fake_enqueue),
    ):
        response = client.post("/api/routing/apply", headers=ha_routing_apply_env["admin_headers"])

    assert response.status_code == 202
    data = response.json()
    assert data["task_id"] == "task-1"
    assert data["queued"] is True
    assert len(enqueued) == 3
    assert enqueued[0][0] == "routing_apply"
    assert enqueued[1][0] == "routing_apply_replica"
    assert enqueued[2][0] == "routing_apply_replica"
    assert "replica «replica-a»" in (enqueued[1][1] or "")
    assert "replica «replica-b»" in (enqueued[2][1] or "")


def test_routing_apply_without_ha_group_enqueues_primary_only(api_test_env):
    client = TestClient(api_test_env["app"])
    enqueued: list[str] = []

    def fake_enqueue(task_type, task_callable, *, created_by_username=None, queued_message=None):
        enqueued.append(task_type)
        return BackgroundTask(id="task-solo", task_type=task_type, status="queued")

    with (
        patch("app.routers.routing.get_active_adapter", return_value=MagicMock()),
        patch.object(background_task_service, "enqueue_background_task", side_effect=fake_enqueue),
    ):
        response = client.post("/api/routing/apply", headers=api_test_env["admin_headers"])

    assert response.status_code == 202
    assert enqueued == ["routing_apply"]


def test_make_routing_apply_for_node_callable_uses_node_adapter():
    adapter = MagicMock()
    adapter.sync_cidr_providers.return_value = {"ok": True}
    adapter.apply_config_changes.return_value = "doall"
    adapter.recreate_profiles.return_value = "profiles"

    node = Node(id=7, name="replica-x", host="10.0.0.7", port=9100, status=NodeStatus.online)
    progress_calls: list[tuple[int, str, str | None]] = []

    def progress_updater(percent, stage, message=None):
        progress_calls.append((percent, stage, message))

    with (
        patch("app.services.background_tasks.SessionLocal") as session_local_mock,
        patch("app.services.node_manager.get_adapter_for_node", return_value=adapter),
    ):
        db = MagicMock()
        db.get.return_value = node
        session_local_mock.return_value = db
        worker = background_task_service.make_routing_apply_for_node_callable(7)
        result = worker(progress_updater=progress_updater)

    adapter.sync_cidr_providers.assert_called_once()
    adapter.apply_config_changes.assert_called_once()
    assert result["message"].startswith("replica-x:")
    assert "replica-x:" in progress_calls[0][1]
    assert '"node_id": 7' in result["output"]
