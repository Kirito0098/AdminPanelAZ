"""Unit tests for HA provider deploy after routing sync (step D.2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.node_sync.groups import serialize_replica_node_ids
from app.services.node_sync.provider_sync import deploy_compiled_providers_to_replicas


@pytest.fixture()
def auto_group_db(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online)
    replica = Node(name="replica", host="10.0.0.2", port=9100, status=NodeStatus.online)
    db_session.add_all([primary, replica])
    db_session.commit()
    group = NodeSyncGroup(
        name="HA",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    db_session.add(group)
    db_session.commit()
    return db_session, group, primary, replica


def _primary_adapter():
    adapter = MagicMock()
    adapter.get_routing_overview.return_value = {
        "providers": [{"filename": "google-ips.txt", "enabled": True, "has_source": True}],
    }
    adapter.get_provider_content.return_value = {
        "filename": "google-ips.txt",
        "content": "8.8.8.8/32\n",
    }
    return adapter


def test_deploy_compiled_providers_uses_run_multi_deploy(auto_group_db):
    db, group, _primary, replica = auto_group_db
    primary_adapter = _primary_adapter()
    deploy_result = {
        "success": True,
        "per_node": [
            {
                "node_id": replica.id,
                "node_name": replica.name,
                "status": "success",
                "pushed_files": ["google-ips.txt"],
                "failed": [],
            }
        ],
        "nodes_deployed": 1,
        "nodes_failed": 0,
        "nodes_skipped": 0,
    }

    with (
        patch(
            "app.services.node_sync.provider_sync._stage_primary_list_files",
            return_value=["google-ips.txt"],
        ) as stage_mock,
        patch(
            "app.services.node_sync.provider_sync.run_multi_deploy",
            return_value=deploy_result,
        ) as deploy_mock,
    ):
        result = deploy_compiled_providers_to_replicas(
            db,
            group,
            primary_adapter,
            sync_result={"sync": {"updated_files": 1}},
        )

    stage_mock.assert_called_once_with(primary_adapter, ["google-ips.txt"])
    deploy_mock.assert_called_once_with(
        db,
        target_node_ids=[replica.id],
        files=["google-ips.txt"],
        sync_after=True,
        apply_after=False,
        triggered_by="ha_routing_sync",
    )
    assert result["success"] is True
    assert result["filenames"] == ["google-ips.txt"]
    assert group.sync_status == SyncStatus.synced


def test_deploy_compiled_providers_manual_mode_skips(auto_group_db):
    db, group, _primary, _replica = auto_group_db
    group.sync_mode = "manual_full"
    db.commit()

    with patch("app.services.node_sync.provider_sync.run_multi_deploy") as deploy_mock:
        result = deploy_compiled_providers_to_replicas(db, group, _primary_adapter())

    assert result["skipped"] is True
    deploy_mock.assert_not_called()
