"""Integration tests for HA provider file auto-sync hook (step D.1)."""

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
def ha_provider_env(api_test_env):
    session_factory = api_test_env["session_factory"]
    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica = Node(name="replica-provider", host="10.0.0.51", port=9100, status=NodeStatus.online)
    db.add(replica)
    db.commit()
    db.refresh(replica)

    group = NodeSyncGroup(
        name="HA provider",
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


def test_put_provider_replicates_to_replicas(ha_provider_env):
    client = TestClient(ha_provider_env["app"])
    primary_adapter = MagicMock()
    primary_adapter.save_provider_content.return_value = {"filename": "google-ips.txt", "cidr_count": 1}
    replica_adapter = MagicMock()
    replica_adapter.save_provider_content.return_value = {"filename": "google-ips.txt", "cidr_count": 1}
    adapter_for_node = _adapter_for_node(
        ha_provider_env["primary_id"],
        primary_adapter,
        ha_provider_env["replica_id"],
        replica_adapter,
    )

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch(
            "app.routers.routing.get_active_node",
            side_effect=lambda db: db.query(Node).filter_by(id=ha_provider_env["primary_id"]).one(),
        ),
        patch("app.services.node_sync.provider_sync.get_adapter_for_node", side_effect=adapter_for_node),
    ):
        response = client.put(
            "/api/routing/providers/google-ips.txt",
            headers=ha_provider_env["admin_headers"],
            json={"content": "8.8.8.8/32\n"},
        )

    assert response.status_code == 200
    assert response.json()["cidr_count"] == 1
    primary_adapter.save_provider_content.assert_called_once_with("google-ips.txt", "8.8.8.8/32\n")
    replica_adapter.save_provider_content.assert_called_once_with("google-ips.txt", "8.8.8.8/32\n")

    db = ha_provider_env["session_factory"]()
    try:
        group = db.query(NodeSyncGroup).filter_by(id=ha_provider_env["group_id"]).one()
        assert group.sync_status == SyncStatus.synced
    finally:
        db.close()


def test_put_provider_replica_failure_does_not_change_api_response(ha_provider_env):
    client = TestClient(ha_provider_env["app"])
    primary_adapter = MagicMock()
    primary_adapter.save_provider_content.return_value = {"filename": "google-ips.txt", "cidr_count": 1}
    replica_adapter = MagicMock()
    replica_adapter.save_provider_content.side_effect = RuntimeError("replica down")
    adapter_for_node = _adapter_for_node(
        ha_provider_env["primary_id"],
        primary_adapter,
        ha_provider_env["replica_id"],
        replica_adapter,
    )

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch(
            "app.routers.routing.get_active_node",
            side_effect=lambda db: db.query(Node).filter_by(id=ha_provider_env["primary_id"]).one(),
        ),
        patch("app.services.node_sync.provider_sync.get_adapter_for_node", side_effect=adapter_for_node),
    ):
        response = client.put(
            "/api/routing/providers/google-ips.txt",
            headers=ha_provider_env["admin_headers"],
            json={"content": "8.8.8.8/32\n"},
        )

    assert response.status_code == 200
    assert response.json()["cidr_count"] == 1
    primary_adapter.save_provider_content.assert_called_once()

    db = ha_provider_env["session_factory"]()
    try:
        group = db.query(NodeSyncGroup).filter_by(id=ha_provider_env["group_id"]).one()
        assert group.sync_status == SyncStatus.failed
        assert group.last_sync_error == "replica down"
    finally:
        db.close()


def test_put_provider_without_ha_group_writes_primary_only(api_test_env):
    client = TestClient(api_test_env["app"])
    primary_adapter = MagicMock()
    primary_adapter.save_provider_content.return_value = {"filename": "google-ips.txt", "cidr_count": 1}

    with patch("app.routers.routing.get_active_adapter", return_value=primary_adapter):
        response = client.put(
            "/api/routing/providers/google-ips.txt",
            headers=api_test_env["admin_headers"],
            json={"content": "8.8.8.8/32\n"},
        )

    assert response.status_code == 200
    primary_adapter.save_provider_content.assert_called_once_with("google-ips.txt", "8.8.8.8/32\n")
