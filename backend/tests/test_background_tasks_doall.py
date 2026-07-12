"""task_run_doall / task_routing_apply: recreate_profiles opt-out for HA replicas."""

from unittest.mock import MagicMock

from app.services.background_tasks import background_task_service


def _adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.apply_config_changes.return_value = "doall ok"
    adapter.recreate_profiles.return_value = "recreate ok"
    adapter.sync_cidr_providers.return_value = {"synced": True}
    return adapter


def test_task_run_doall_recreates_profiles_by_default():
    adapter = _adapter()
    result = background_task_service.task_run_doall(adapter)
    adapter.apply_config_changes.assert_called_once()
    adapter.recreate_profiles.assert_called_once()
    assert "recreate ok" in result["output"]


def test_task_run_doall_skips_recreate_when_disabled():
    adapter = _adapter()
    result = background_task_service.task_run_doall(adapter, recreate_profiles=False)
    adapter.apply_config_changes.assert_called_once()
    adapter.recreate_profiles.assert_not_called()
    assert "recreate ok" not in result["output"]


def test_task_routing_apply_passes_recreate_flag_down():
    adapter = _adapter()
    background_task_service.task_routing_apply(adapter, recreate_profiles=False)
    adapter.sync_cidr_providers.assert_called_once()
    adapter.apply_config_changes.assert_called_once()
    adapter.recreate_profiles.assert_not_called()


def test_task_routing_apply_default_recreates():
    adapter = _adapter()
    background_task_service.task_routing_apply(adapter)
    adapter.recreate_profiles.assert_called_once()
