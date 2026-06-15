"""Node sync reconcile worker tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.node_sync.groups import serialize_replica_node_ids
from app.services.node_sync.reconcile_worker import reconcile_sync_groups_once


@pytest.fixture()
def group_db(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online)
    replica = Node(name="replica", host="10.0.0.2", port=9100, status=NodeStatus.online)
    db_session.add_all([primary, replica])
    db_session.commit()
    group = NodeSyncGroup(
        name="HA",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_status=SyncStatus.synced,
    )
    db_session.add(group)
    db_session.commit()
    return db_session, group


def test_reconcile_marks_failed_on_drift(group_db):
    db, group = group_db

    with patch(
        "app.services.node_sync.reconcile_worker.verify_sync_group",
        return_value={"ready": False, "summary": "mismatch"},
    ), patch(
        "app.services.node_sync.reconcile_worker.SessionLocal",
        return_value=db,
    ), patch.object(db, "close"):
        result = reconcile_sync_groups_once()

    assert result["node_sync_reconcile"] == "ok"
    assert len(result["drift"]) == 1
    db.refresh(group)
    assert group.sync_status == SyncStatus.failed
