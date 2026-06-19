"""Integration tests for HA AntiZapret settings auto-sync hook (step C.2)."""

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
def ha_antizapret_env(api_test_env):
    session_factory = api_test_env["session_factory"]
    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica = Node(name="replica-az", host="10.0.0.31", port=9100, status=NodeStatus.online)
    db.add(replica)
    db.commit()
    db.refresh(replica)

    group = NodeSyncGroup(
        name="HA antizapret",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    db.add(group)
    db.commit()

    primary_id = primary.id
    replica_id = replica.id
    group_id = group.id
    db.close()

    _set_active_node(session_factory, primary_id)
    yield {
        **api_test_env,
        "primary_id": primary_id,
        "replica_id": replica_id,
        "group_id": group_id,
    }


def _adapter_for_node(primary_id, primary_adapter, replica_id, replica_adapter):
    def resolve(node):
        if node.id == replica_id:
            return replica_adapter
        if node.id == primary_id:
            return primary_adapter
        return MagicMock()

    return resolve


def test_put_antizapret_settings_replicates_to_replicas(ha_antizapret_env):
    client = TestClient(ha_antizapret_env["app"])
    primary_adapter = MagicMock()
    primary_adapter.update_antizapret_settings.return_value = {
        "success": True,
        "message": "Настройки сохранены",
        "changes": 1,
        "needs_apply": True,
    }
    replica_adapter = MagicMock()
    replica_adapter.update_antizapret_settings.return_value = {
        "success": True,
        "changes": 1,
        "needs_apply": True,
    }
    adapter_for_node = _adapter_for_node(
        ha_antizapret_env["primary_id"],
        primary_adapter,
        ha_antizapret_env["replica_id"],
        replica_adapter,
    )

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch(
            "app.routers.routing.get_active_node",
            side_effect=lambda db: db.query(Node).filter_by(id=ha_antizapret_env["primary_id"]).one(),
        ),
        patch("app.services.node_sync.antizapret_sync.get_adapter_for_node", side_effect=adapter_for_node),
    ):
        response = client.put(
            "/api/routing/antizapret-settings",
            headers=ha_antizapret_env["admin_headers"],
            json={"route_all": True, "unknown": "skip", "ANTIZAPRET_WARP": "y"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["changes"] == 1
    assert data["needs_apply"] is True
    primary_adapter.update_antizapret_settings.assert_called_once_with(
        {"route_all": True, "ANTIZAPRET_WARP": "y"}
    )
    replica_adapter.update_antizapret_settings.assert_called_once_with({"route_all": True})

    db = ha_antizapret_env["session_factory"]()
    try:
        group = db.query(NodeSyncGroup).filter_by(id=ha_antizapret_env["group_id"]).one()
        assert group.sync_status == SyncStatus.synced
    finally:
        db.close()


def test_put_antizapret_settings_replica_failure_does_not_change_api_response(ha_antizapret_env):
    client = TestClient(ha_antizapret_env["app"])
    primary_adapter = MagicMock()
    primary_adapter.update_antizapret_settings.return_value = {
        "success": True,
        "message": "Настройки сохранены",
        "changes": 1,
        "needs_apply": False,
    }
    replica_adapter = MagicMock()
    replica_adapter.update_antizapret_settings.side_effect = RuntimeError("replica down")
    adapter_for_node = _adapter_for_node(
        ha_antizapret_env["primary_id"],
        primary_adapter,
        ha_antizapret_env["replica_id"],
        replica_adapter,
    )

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch(
            "app.routers.routing.get_active_node",
            side_effect=lambda db: db.query(Node).filter_by(id=ha_antizapret_env["primary_id"]).one(),
        ),
        patch("app.services.node_sync.antizapret_sync.get_adapter_for_node", side_effect=adapter_for_node),
    ):
        response = client.put(
            "/api/routing/antizapret-settings",
            headers=ha_antizapret_env["admin_headers"],
            json={"route_all": "y"},
        )

    assert response.status_code == 200
    assert response.json()["changes"] == 1
    primary_adapter.update_antizapret_settings.assert_called_once()

    db = ha_antizapret_env["session_factory"]()
    try:
        group = db.query(NodeSyncGroup).filter_by(id=ha_antizapret_env["group_id"]).one()
        assert group.sync_status == SyncStatus.failed
        assert group.last_sync_error == "replica down"
    finally:
        db.close()


def test_put_antizapret_settings_apply_true_enqueues_routing_tasks(ha_antizapret_env):
    client = TestClient(ha_antizapret_env["app"])
    primary_adapter = MagicMock()
    primary_adapter.update_antizapret_settings.return_value = {
        "success": True,
        "message": "Настройки сохранены",
        "changes": 1,
        "needs_apply": True,
    }
    replica_adapter = MagicMock()
    enqueued: list[str] = []
    task_counter = {"n": 0}

    def fake_enqueue(task_type, task_callable, *, created_by_username=None, queued_message=None):
        task_counter["n"] += 1
        enqueued.append(task_type)
        return BackgroundTask(
            id=f"task-{task_counter['n']}",
            task_type=task_type,
            status="queued",
        )

    adapter_for_node = _adapter_for_node(
        ha_antizapret_env["primary_id"],
        primary_adapter,
        ha_antizapret_env["replica_id"],
        replica_adapter,
    )

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch(
            "app.routers.routing.get_active_node",
            side_effect=lambda db: db.query(Node).filter_by(id=ha_antizapret_env["primary_id"]).one(),
        ),
        patch("app.services.node_sync.antizapret_sync.get_adapter_for_node", side_effect=adapter_for_node),
        patch.object(background_task_service, "find_active_task", return_value=None),
        patch.object(background_task_service, "enqueue_background_task", side_effect=fake_enqueue),
    ):
        response = client.put(
            "/api/routing/antizapret-settings?apply=true",
            headers=ha_antizapret_env["admin_headers"],
            json={"route_all": True},
        )

    assert response.status_code == 200
    assert response.json()["needs_apply"] is True
    assert enqueued == ["routing_apply", "routing_apply_replica"]
    replica_adapter.update_antizapret_settings.assert_called_once_with({"route_all": True})


def test_put_antizapret_settings_apply_true_ignored_without_ha_group(api_test_env):
    client = TestClient(api_test_env["app"])
    primary_adapter = MagicMock()
    primary_adapter.update_antizapret_settings.return_value = {
        "success": True,
        "message": "Настройки сохранены",
        "changes": 1,
        "needs_apply": True,
    }

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch.object(background_task_service, "enqueue_background_task") as enqueue_mock,
    ):
        response = client.put(
            "/api/routing/antizapret-settings?apply=true",
            headers=api_test_env["admin_headers"],
            json={"route_all": True},
        )

    assert response.status_code == 200
    enqueue_mock.assert_not_called()
