"""Integration tests for HA routing sync deploy hook (step D.2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import AppSetting, Node, NodeStatus, NodeSyncGroup, SyncStatus
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
def ha_routing_sync_env(api_test_env):
    session_factory = api_test_env["session_factory"]
    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica1 = Node(name="replica-sync-a", host="10.0.0.61", port=9100, status=NodeStatus.online)
    replica2 = Node(name="replica-sync-b", host="10.0.0.62", port=9100, status=NodeStatus.online)
    db.add_all([replica1, replica2])
    db.commit()
    db.refresh(replica1)
    db.refresh(replica2)

    group = NodeSyncGroup(
        name="HA routing sync",
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
    group_id = group.id
    db.close()

    _set_active_node(session_factory, primary_id)
    yield {
        **api_test_env,
        "primary_id": primary_id,
        "replica_ids": replica_ids,
        "group_id": group_id,
    }


def _primary_adapter():
    adapter = MagicMock()
    adapter.sync_cidr_providers.return_value = {
        "restored": {},
        "sync": {"synced_files": 1, "updated_files": 1, "missing_sources": []},
    }
    adapter.get_routing_overview.return_value = {
        "providers": [
            {
                "filename": "google-ips.txt",
                "enabled": True,
                "has_source": True,
            },
            {
                "filename": "amazon-ips.txt",
                "enabled": False,
                "has_source": True,
            },
        ],
    }
    adapter.get_provider_content.return_value = {
        "filename": "google-ips.txt",
        "content": "8.8.8.8/32\n",
    }
    return adapter


def test_routing_sync_ha_compiles_primary_and_deploys_to_replicas(ha_routing_sync_env):
    client = TestClient(ha_routing_sync_env["app"])
    primary_adapter = _primary_adapter()
    deploy_result = {
        "success": True,
        "message": "ok",
        "artifact_stamp": "abc",
        "per_node": [
            {
                "node_id": ha_routing_sync_env["replica_ids"][0],
                "node_name": "replica-sync-a",
                "status": "success",
                "pushed_files": ["google-ips.txt"],
                "failed": [],
            },
            {
                "node_id": ha_routing_sync_env["replica_ids"][1],
                "node_name": "replica-sync-b",
                "status": "success",
                "pushed_files": ["google-ips.txt"],
                "failed": [],
            },
        ],
        "deploy": {"pushed": ["google-ips.txt"], "failed": []},
        "nodes_deployed": 2,
        "nodes_failed": 0,
        "nodes_skipped": 0,
    }

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch(
            "app.routers.routing.get_active_node",
            side_effect=lambda db: db.query(Node).filter_by(id=ha_routing_sync_env["primary_id"]).one(),
        ),
        patch(
            "app.services.node_sync.provider_sync.run_multi_deploy",
            return_value=deploy_result,
        ) as run_multi_deploy,
        patch("app.services.node_sync.provider_sync._stage_primary_list_files", return_value=["google-ips.txt"]),
    ):
        response = client.post("/api/routing/sync", headers=ha_routing_sync_env["admin_headers"])

    assert response.status_code == 200
    data = response.json()
    assert data["sync"]["updated_files"] == 1
    assert data["ha_deploy"]["success"] is True
    assert data["ha_deploy"]["filenames"] == ["google-ips.txt"]
    primary_adapter.sync_cidr_providers.assert_called_once()
    run_multi_deploy.assert_called_once()
    call_kwargs = run_multi_deploy.call_args.kwargs
    assert call_kwargs["target_node_ids"] == ha_routing_sync_env["replica_ids"]
    assert call_kwargs["files"] == ["google-ips.txt"]
    assert call_kwargs["sync_after"] is True
    assert call_kwargs["apply_after"] is False

    db = ha_routing_sync_env["session_factory"]()
    try:
        group = db.query(NodeSyncGroup).filter_by(id=ha_routing_sync_env["group_id"]).one()
        assert group.sync_status == SyncStatus.synced
    finally:
        db.close()


def test_routing_sync_without_ha_group_compiles_primary_only(api_test_env):
    client = TestClient(api_test_env["app"])
    primary_adapter = _primary_adapter()

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch("app.services.node_sync.provider_sync.run_multi_deploy") as run_multi_deploy,
    ):
        response = client.post("/api/routing/sync", headers=api_test_env["admin_headers"])

    assert response.status_code == 200
    assert "ha_deploy" not in response.json()
    primary_adapter.sync_cidr_providers.assert_called_once()
    run_multi_deploy.assert_not_called()


def test_routing_sync_ha_deploy_failure_does_not_change_primary_response(ha_routing_sync_env):
    client = TestClient(ha_routing_sync_env["app"])
    primary_adapter = _primary_adapter()
    deploy_result = {
        "success": False,
        "message": "failed",
        "artifact_stamp": "abc",
        "per_node": [
            {
                "node_id": ha_routing_sync_env["replica_ids"][0],
                "node_name": "replica-sync-a",
                "status": "failed",
                "pushed_files": [],
                "failed": [{"file": "google-ips.txt", "error": "connection refused"}],
                "error": "deploy failed",
            },
        ],
        "deploy": {"pushed": [], "failed": [{"file": "google-ips.txt", "error": "connection refused"}]},
        "nodes_deployed": 0,
        "nodes_failed": 1,
        "nodes_skipped": 0,
    }

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch(
            "app.routers.routing.get_active_node",
            side_effect=lambda db: db.query(Node).filter_by(id=ha_routing_sync_env["primary_id"]).one(),
        ),
        patch("app.services.node_sync.provider_sync.run_multi_deploy", return_value=deploy_result),
        patch("app.services.node_sync.provider_sync._stage_primary_list_files", return_value=["google-ips.txt"]),
    ):
        response = client.post("/api/routing/sync", headers=ha_routing_sync_env["admin_headers"])

    assert response.status_code == 200
    assert response.json()["sync"]["updated_files"] == 1
    assert response.json()["ha_deploy"]["success"] is False

    db = ha_routing_sync_env["session_factory"]()
    try:
        group = db.query(NodeSyncGroup).filter_by(id=ha_routing_sync_env["group_id"]).one()
        assert group.sync_status == SyncStatus.failed
    finally:
        db.close()
