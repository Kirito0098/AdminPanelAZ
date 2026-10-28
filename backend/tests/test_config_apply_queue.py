"""Focused coverage: async config apply / AWG2 HA enqueue (no sync hang)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import config_apply_queue as queue


def test_enqueue_ha_awg2_sync_returns_none_without_group():
    with (
        patch.object(queue, "SessionLocal") as session_local,
        patch.object(queue, "find_sync_group_for_primary", return_value=None),
        patch.object(queue.background_task_service, "enqueue_background_task") as enqueue,
    ):
        session_local.return_value = MagicMock()
        assert queue.enqueue_ha_awg2_sync(primary_node_id=1) is None
        enqueue.assert_not_called()


def test_enqueue_ha_awg2_sync_queues_with_group_lock_subject():
    group = SimpleNamespace(id=42)
    task = SimpleNamespace(id="awg2-task-1")
    with (
        patch.object(queue, "SessionLocal") as session_local,
        patch.object(queue, "find_sync_group_for_primary", return_value=group),
        patch.object(queue.background_task_service, "enqueue_background_task", return_value=task) as enqueue,
    ):
        session_local.return_value = MagicMock()
        result = queue.enqueue_ha_awg2_sync(primary_node_id=7, created_by_username="admin")
    assert result is task
    assert enqueue.call_args.args[0] == queue.HA_AWG2_SYNC_TASK
    assert enqueue.call_args.kwargs["subject_key"] == "ha-group:42"


def test_enqueue_doall_and_replicate_passes_recreate_profiles_false():
    task = SimpleNamespace(id="cfg-1")
    node = SimpleNamespace(id=3, name="primary", openvpn_multihome=False)
    adapter = MagicMock()
    captured: dict = {}

    def fake_doall(_adapter, _progress, **kwargs):
        captured.update(kwargs)
        return {"output": "ok"}

    db = MagicMock()
    db.get.return_value = node

    with (
        patch.object(queue, "SessionLocal", return_value=db),
        patch.object(queue, "get_adapter_for_node", return_value=adapter),
        patch.object(queue.background_task_service, "task_run_doall", side_effect=fake_doall),
        patch.object(queue, "maybe_replicate_config_files") as replicate,
        patch.object(queue.background_task_service, "enqueue_background_task", return_value=task) as enqueue,
    ):
        result = queue.enqueue_doall_and_replicate(
            node_id=3,
            file_keys=["include_hosts"],
            content_overrides={"include_hosts": "a.com"},
            created_by_username="admin",
        )
        callable_fn = enqueue.call_args.args[1]
        callable_fn(None)

    assert result is task
    assert captured.get("recreate_profiles") is False
    replicate.assert_called_once()
    db.commit.assert_called_once()
