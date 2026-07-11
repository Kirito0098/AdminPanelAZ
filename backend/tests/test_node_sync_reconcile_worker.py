import json
from unittest.mock import MagicMock, patch

from app.models import SyncStatus
from app.services.node_sync import reconcile_worker


def _make_group(*, sync_status=SyncStatus.synced, last_verify_result=None):
    group = MagicMock()
    group.id = 1
    group.name = "test-ha"
    group.shared_domain = "vpn.example.com"
    group.sync_mode = "auto"
    group.sync_status = sync_status
    group.last_verify_result = last_verify_result
    group.last_sync_error = None
    return group


def test_reconcile_skips_pending_groups():
    pending = _make_group(sync_status=SyncStatus.pending)
    synced = _make_group(sync_status=SyncStatus.synced)

    with patch.object(reconcile_worker, "SessionLocal") as session_local:
        db = MagicMock()
        session_local.return_value = db
        db.query.return_value.order_by.return_value.all.return_value = [pending, synced]

        with patch.object(reconcile_worker, "verify_sync_group") as verify:
            verify.return_value = {"ready": True, "summary": "ok"}
            result = reconcile_worker.reconcile_sync_groups_once()

    assert result["checked"] == 1
    verify.assert_called_once()


def test_auto_heal_failure_counter_accumulates_and_notifies():
    group = _make_group(
        last_verify_result=json.dumps({"ready": False, "auto_heal_failures": 1}),
    )
    not_ready = {"ready": False, "summary": "drift"}

    with patch.object(reconcile_worker, "SessionLocal") as session_local:
        db = MagicMock()
        session_local.return_value = db
        db.query.return_value.order_by.return_value.all.return_value = [group]

        with patch.object(reconcile_worker.settings, "node_sync_auto_heal", True):
            with patch.object(reconcile_worker.settings, "node_sync_auto_heal_max_failures", 3):
                with patch.object(reconcile_worker, "is_auto_sync_enabled", return_value=True):
                    with patch.object(reconcile_worker, "verify_sync_group", return_value=not_ready):
                        with patch.object(
                            reconcile_worker,
                            "_attempt_incremental_heal",
                            return_value=(False, ["heal failed"]),
                        ):
                            result = reconcile_worker.reconcile_sync_groups_once()

    drift = result["drift"]
    assert len(drift) == 1
    assert drift[0]["auto_heal_failures"] == 2
    assert drift[0]["notify"] is False

    persisted = json.loads(group.last_verify_result)
    assert persisted["auto_heal_failures"] == 2


def test_auto_heal_exhausted_notifies_with_push_full_hint():
    group = _make_group(
        last_verify_result=json.dumps({"ready": False, "auto_heal_failures": 2}),
    )
    not_ready = {"ready": False, "summary": "drift"}

    with patch.object(reconcile_worker, "SessionLocal") as session_local:
        db = MagicMock()
        session_local.return_value = db
        db.query.return_value.order_by.return_value.all.return_value = [group]

        with patch.object(reconcile_worker.settings, "node_sync_auto_heal", True):
            with patch.object(reconcile_worker.settings, "node_sync_auto_heal_max_failures", 3):
                with patch.object(reconcile_worker, "is_auto_sync_enabled", return_value=True):
                    with patch.object(reconcile_worker, "verify_sync_group", return_value=not_ready):
                        with patch.object(
                            reconcile_worker,
                            "_attempt_incremental_heal",
                            return_value=(False, ["heal failed"]),
                        ):
                            result = reconcile_worker.reconcile_sync_groups_once()

    drift = result["drift"]
    assert drift[0]["auto_heal_failures"] == 3
    assert drift[0]["notify"] is True
    assert "Push full" in drift[0]["hint"]
