"""Node sync reconcile worker tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.node_sync.groups import serialize_replica_node_ids
from app.services.node_sync.reconcile_worker import (
    classify_heal_actions,
    reconcile_sync_groups_once,
    reconcile_sync_groups_safe,
)


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
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    db_session.add(group)
    db_session.commit()
    return db_session, group


def _drift_verify(*, path: str = "antizapret/config", heal_failures: int = 0) -> dict:
    return {
        "ready": False,
        "summary": "расхождения между primary и replica",
        "replicas": [
            {
                "node_id": 2,
                "node_name": "replica",
                "online": True,
                "mismatches": [{"kind": "fingerprint", "path": path}],
            }
        ],
        "auto_heal_failures": heal_failures,
    }


def test_classify_heal_actions_config_and_antizapret():
    actions, unhealable = classify_heal_actions(_drift_verify())
    assert actions == {"config", "antizapret"}
    assert unhealable is False


def test_classify_heal_actions_client_drift_uses_policy():
    verify = {
        "ready": False,
        "replicas": [
            {
                "online": True,
                "mismatches": [{"kind": "openvpn_clients", "only_primary": ["alice"]}],
            }
        ],
    }
    actions, unhealable = classify_heal_actions(verify)
    assert actions == {"policy"}
    assert unhealable is False


def test_classify_heal_actions_pki_unhealable_only():
    verify = {
        "ready": False,
        "replicas": [
            {
                "online": True,
                "mismatches": [{"kind": "fingerprint", "path": "easyrsa3/pki/index.txt"}],
            }
        ],
    }
    actions, unhealable = classify_heal_actions(verify)
    assert actions == set()
    assert unhealable is True


def test_reconcile_marks_failed_on_drift_without_auto_heal(group_db):
    db, group = group_db

    with patch(
        "app.services.node_sync.reconcile_worker.verify_sync_group",
        return_value={"ready": False, "summary": "mismatch"},
    ), patch(
        "app.services.node_sync.reconcile_worker.settings",
        MagicMock(node_sync_auto_heal=False, node_sync_auto_heal_max_failures=3),
    ), patch(
        "app.services.node_sync.reconcile_worker.SessionLocal",
        return_value=db,
    ), patch.object(db, "close"):
        result = reconcile_sync_groups_once()

    assert result["node_sync_reconcile"] == "ok"
    assert len(result["drift"]) == 1
    assert result["drift"][0]["notify"] is True
    db.refresh(group)
    assert group.sync_status == SyncStatus.failed


def test_reconcile_auto_heal_success_resets_failures(group_db):
    db, group = group_db
    drift = _drift_verify()
    healed = {"ready": True, "summary": "ready for DNS failover", "auto_heal_failures": 2}

    with patch(
        "app.services.node_sync.reconcile_worker.verify_sync_group",
        side_effect=[drift, healed],
    ), patch(
        "app.services.node_sync.reconcile_worker.settings",
        MagicMock(node_sync_auto_heal=True, node_sync_auto_heal_max_failures=3),
    ), patch(
        "app.services.node_sync.reconcile_worker.heal_config_drift",
        return_value={"success": True, "errors": []},
    ) as heal_config, patch(
        "app.services.node_sync.reconcile_worker.heal_antizapret_drift",
        return_value={"success": True, "errors": []},
    ) as heal_antizapret, patch(
        "app.services.node_sync.reconcile_worker.heal_policy_drift",
    ) as heal_policy, patch(
        "app.services.node_sync.reconcile_worker.SessionLocal",
        return_value=db,
    ), patch.object(db, "close"):
        result = reconcile_sync_groups_once()

    heal_config.assert_called_once()
    heal_antizapret.assert_called_once()
    heal_policy.assert_not_called()
    assert result["drift"] == []
    db.refresh(group)
    assert group.sync_status == SyncStatus.synced
    stored = json.loads(group.last_verify_result or "{}")
    assert stored["auto_heal_failures"] == 0


def test_reconcile_auto_heal_suppresses_notify_until_max_failures(group_db):
    db, group = group_db
    drift = _drift_verify(heal_failures=1)

    mock_settings = MagicMock(node_sync_auto_heal=True, node_sync_auto_heal_max_failures=3)

    with patch(
        "app.services.node_sync.reconcile_worker.verify_sync_group",
        return_value=drift,
    ), patch(
        "app.services.node_sync.reconcile_worker.settings",
        mock_settings,
    ), patch(
        "app.services.node_sync.reconcile_worker._attempt_incremental_heal",
        return_value=(False, ["transfer failed"]),
    ), patch(
        "app.services.node_sync.reconcile_worker._notify_drift",
    ) as notify, patch(
        "app.services.node_sync.reconcile_worker.SessionLocal",
        return_value=db,
    ), patch.object(db, "close"):
        reconcile_sync_groups_safe()

    notify.assert_not_called()
    db.refresh(group)
    stored = json.loads(group.last_verify_result or "{}")
    assert stored["auto_heal_failures"] == 2
    assert group.sync_status == SyncStatus.failed


def test_reconcile_auto_heal_notifies_after_max_failures(group_db):
    db, group = group_db
    drift = _drift_verify(heal_failures=2)

    mock_settings = MagicMock(node_sync_auto_heal=True, node_sync_auto_heal_max_failures=3)

    with patch(
        "app.services.node_sync.reconcile_worker.verify_sync_group",
        return_value=drift,
    ), patch(
        "app.services.node_sync.reconcile_worker.settings",
        mock_settings,
    ), patch(
        "app.services.node_sync.reconcile_worker._attempt_incremental_heal",
        return_value=(False, ["transfer failed"]),
    ), patch(
        "app.services.node_sync.reconcile_worker._notify_drift",
    ) as notify, patch(
        "app.services.node_sync.reconcile_worker.SessionLocal",
        return_value=db,
    ), patch.object(db, "close"):
        result = reconcile_sync_groups_safe()

    notify.assert_called_once()
    notified = notify.call_args[0][0]
    assert notified[0]["auto_heal_failures"] == 3
    assert notified[0]["hint"]
    assert result["drift"][0]["notify"] is True


def test_reconcile_auto_heal_never_push_full(group_db):
    db, group = group_db

    with patch(
        "app.services.node_sync.reconcile_worker.verify_sync_group",
        return_value=_drift_verify(),
    ), patch(
        "app.services.node_sync.reconcile_worker.settings",
        MagicMock(node_sync_auto_heal=True, node_sync_auto_heal_max_failures=3),
    ), patch(
        "app.services.node_sync.reconcile_worker.heal_config_drift",
        return_value={"success": True, "errors": []},
    ), patch(
        "app.services.node_sync.reconcile_worker.heal_antizapret_drift",
        return_value={"success": True, "errors": []},
    ), patch(
        "app.services.node_sync.reconcile_worker.run_push_full",
        create=True,
    ) as push_full, patch(
        "app.services.node_sync.push_full.run_push_full",
    ) as push_full_module, patch(
        "app.services.node_sync.reconcile_worker.SessionLocal",
        return_value=db,
    ), patch.object(db, "close"):
        reconcile_sync_groups_once()

    push_full.assert_not_called()
    push_full_module.assert_not_called()


def test_reconcile_auto_heal_routes_policy_drift(group_db):
    db, group = group_db
    verify = {
        "ready": False,
        "summary": "расхождения",
        "replicas": [
            {
                "online": True,
                "mismatches": [{"kind": "wireguard_clients", "only_primary": ["wg-user"]}],
            }
        ],
    }

    with patch(
        "app.services.node_sync.reconcile_worker.verify_sync_group",
        side_effect=[verify, {"ready": True, "summary": "ok"}],
    ), patch(
        "app.services.node_sync.reconcile_worker.settings",
        MagicMock(node_sync_auto_heal=True, node_sync_auto_heal_max_failures=3),
    ), patch(
        "app.services.node_sync.reconcile_worker.heal_policy_drift",
        return_value={"success": True, "errors": []},
    ) as heal_policy, patch(
        "app.services.node_sync.reconcile_worker.heal_config_drift",
    ) as heal_config, patch(
        "app.services.node_sync.reconcile_worker.heal_antizapret_drift",
    ) as heal_antizapret, patch(
        "app.services.node_sync.reconcile_worker.SessionLocal",
        return_value=db,
    ), patch.object(db, "close"):
        reconcile_sync_groups_once()

    heal_policy.assert_called_once()
    heal_config.assert_not_called()
    heal_antizapret.assert_not_called()
