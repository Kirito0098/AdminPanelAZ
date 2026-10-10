"""Background handlers leave a pending group alone: the running sync task owns its status."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models import SyncStatus, VpnType
from app.services.node_sync import reconcile_worker, vpn_state_sync
from app.services.node_sync.replicate import ReplicateOperation, ReplicateResult, finalize_replicate_outcome


def _db_with_committed_status(*statuses: SyncStatus) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.side_effect = list(statuses)
    return db


def _group(status: SyncStatus) -> MagicMock:
    group = MagicMock()
    group.id = 1
    group.name = "ha"
    group.shared_domain = "vpn.example.com"
    group.sync_mode = "auto"
    group.sync_status = status
    group.last_sync_error = None
    group.last_verify_result = None
    return group


def test_finalize_keeps_status_of_pending_group():
    db = _db_with_committed_status(SyncStatus.pending)
    group = _group(SyncStatus.pending)
    result = ReplicateResult(operation=ReplicateOperation.CLIENT_CREATE)
    result.errors.append({"node_id": 2, "node_name": "replica", "error": "offline"})

    finalize_replicate_outcome(db, group, result)

    assert group.sync_status == SyncStatus.pending
    assert group.last_sync_error is None
    db.commit.assert_called_once()


def test_primary_crypto_copy_keeps_status_of_pending_group(monkeypatch):
    db = _db_with_committed_status(SyncStatus.pending)
    group = _group(SyncStatus.pending)
    replica = MagicMock(id=2)
    replica.name = "replica"
    monkeypatch.setattr("app.services.node_sync.groups.get_replica_nodes", lambda _db, _group: [replica])
    monkeypatch.setattr("app.services.node_sync.replicate._primary_adapter", lambda _db, _group: MagicMock())
    monkeypatch.setattr("app.services.node_manager.get_adapter_for_node", lambda _node: MagicMock())
    monkeypatch.setattr(
        vpn_state_sync, "sync_vpn_crypto_from_primary", MagicMock(side_effect=RuntimeError("offline"))
    )

    result = vpn_state_sync.replicate_primary_crypto_to_replicas(
        db, group, MagicMock(client_name="alice", vpn_type=VpnType.wireguard)
    )

    assert [entry["node_id"] for entry in result["errors"]] == [2]
    assert group.sync_status == SyncStatus.pending
    assert group.last_sync_error is None


@pytest.mark.parametrize(
    "committed",
    [
        (SyncStatus.pending,),
        (SyncStatus.synced, SyncStatus.pending),
    ],
    ids=["pending-before-heal", "pending-before-failed"],
)
def test_reconcile_does_not_fail_group_that_became_pending(committed):
    group = _group(SyncStatus.synced)
    db = _db_with_committed_status(*committed)
    db.query.return_value.order_by.return_value.all.return_value = [group]

    with patch.object(reconcile_worker, "SessionLocal", return_value=db), patch.object(
        reconcile_worker.settings, "node_sync_auto_heal", False
    ), patch.object(
        reconcile_worker, "verify_sync_group", return_value={"ready": False, "summary": "drift"}
    ):
        result = reconcile_worker.reconcile_sync_groups_once()

    assert result["node_sync_reconcile"] == "ok"
    assert result["drift"] == []
    assert group.sync_status == SyncStatus.synced
    assert group.last_sync_error is None
