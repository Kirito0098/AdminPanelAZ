"""Unit tests for CIDR pipeline orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.cidr.pipeline.orchestrator import (
    run_apply,
    run_compile,
    run_deploy,
    run_ingest,
    run_multi_deploy,
)
from app.services.node_adapter import RemoteNodeAdapter


@pytest.fixture
def mock_db():
    return MagicMock()


def test_run_ingest_delegates_to_refresh_all_providers(mock_db):
    with patch("app.services.cidr.pipeline.orchestrator.CidrDbUpdaterService") as svc_cls, patch(
        "app.services.cidr.pipeline.orchestrator.maybe_notify_ingest_partial"
    ) as notify:
        svc = svc_cls.return_value
        svc.refresh_all_providers.return_value = {"success": True, "providers_updated": 2}

        result = run_ingest(
            mock_db,
            triggered_by="manual:admin",
            selected_files=["aws.txt"],
            dry_run=True,
        )

    svc_cls.assert_called_once_with(db=mock_db)
    svc.refresh_all_providers.assert_called_once_with(
        triggered_by="manual:admin",
        selected_files=["aws.txt"],
        progress_callback=None,
        dry_run=True,
    )
    notify.assert_called_once()
    assert result == {"success": True, "providers_updated": 2}


def test_run_compile_delegates_to_update_cidr_files_from_db():
    with patch("app.services.cidr.pipeline.orchestrator.update_cidr_files_from_db") as compile_fn, patch(
        "app.services.cidr.pipeline.orchestrator.compute_artifact_stamp", return_value="deadbeef01"
    ):
        compile_fn.return_value = {"success": True, "updated": ["aws.txt"]}
        callback = MagicMock()

        result = run_compile(
            progress_callback=callback,
            selected_files=["aws.txt"],
            region_scopes=["eu"],
        )

    compile_fn.assert_called_once_with(
        progress_callback=callback,
        selected_files=["aws.txt"],
        region_scopes=["eu"],
    )
    assert result == {"success": True, "updated": ["aws.txt"], "artifact_stamp": "deadbeef01"}


def test_run_deploy_local_calls_sync():
    adapter = MagicMock()
    adapter.sync_cidr_providers.return_value = {"restored": [], "sync": {"changed": 1}}

    result = run_deploy(adapter, files=["aws.txt"])

    adapter.sync_cidr_providers.assert_called_once()
    assert result["mode"] == "local"
    assert result["sync"] == {"restored": [], "sync": {"changed": 1}}


def test_run_deploy_remote_pushes_and_syncs():
    adapter = RemoteNodeAdapter("10.0.0.1", 8443, "secret-key")

    with patch("app.services.cidr.pipeline.orchestrator.push_cidr_artifacts") as push_fn, patch.object(
        adapter, "sync_cidr_providers", return_value={"changed": 2}
    ) as sync_fn:
        push_fn.return_value = {
            "pushed": ["aws.txt", "google.txt"],
            "failed": [],
            "skipped": [],
        }
        result = run_deploy(adapter, files=["aws.txt", "google.txt"])

    push_fn.assert_called_once_with(adapter, filenames=["aws.txt", "google.txt"])
    sync_fn.assert_called_once()
    assert result["mode"] == "remote"
    assert result["pushed"] == ["aws.txt", "google.txt"]
    assert result["failed"] == []
    assert result["sync"] == {"changed": 2}


def test_run_apply_sync_only():
    adapter = MagicMock()
    adapter.sync_cidr_providers.return_value = {"sync": {"ok": True}}

    result = run_apply(adapter, sync_after=True, apply_after=False)

    adapter.sync_cidr_providers.assert_called_once()
    adapter.apply_config_changes.assert_not_called()
    assert result == {"sync": {"sync": {"ok": True}}}


def test_run_apply_sync_and_doall():
    adapter = MagicMock()
    adapter.sync_cidr_providers.return_value = {"sync": {"ok": True}}
    adapter.apply_config_changes.return_value = "doall completed"

    result = run_apply(adapter, sync_after=True, apply_after=True)

    adapter.sync_cidr_providers.assert_called_once()
    adapter.apply_config_changes.assert_called_once()
    assert result["sync"] == {"sync": {"ok": True}}
    assert result["doall_output"] == "doall completed"


def test_run_apply_doall_only():
    adapter = MagicMock()

    result = run_apply(adapter, sync_after=False, apply_after=True)

    adapter.sync_cidr_providers.assert_not_called()
    adapter.apply_config_changes.assert_called_once()
    adapter.recreate_profiles.assert_not_called()
    assert result == {"doall_output": adapter.apply_config_changes.return_value}


def test_run_apply_doall_and_recreate_profiles():
    adapter = MagicMock()
    adapter.apply_config_changes.return_value = "doall completed"
    adapter.recreate_profiles.return_value = "profiles recreated"

    result = run_apply(adapter, sync_after=False, apply_after=True, recreate_profiles_after=True)

    adapter.apply_config_changes.assert_called_once()
    adapter.recreate_profiles.assert_called_once()
    assert result["doall_output"] == "doall completed"
    assert result["recreate_profiles_output"] == "profiles recreated"


def test_run_multi_deploy_apply_only_when_requested(mock_db):
    node = MagicMock()
    node.id = 7
    node.name = "remote"
    node.status = "online"

    adapter = MagicMock()
    with patch("app.services.cidr.pipeline.orchestrator.resolve_deploy_targets", return_value=([node], [])), patch(
        "app.services.cidr.pipeline.orchestrator.get_adapter_for_node", return_value=adapter
    ), patch("app.services.cidr.pipeline.orchestrator.run_deploy") as deploy_fn, patch(
        "app.services.cidr.pipeline.orchestrator.run_apply"
    ) as apply_fn, patch(
        "app.services.cidr.pipeline.orchestrator.compute_artifact_stamp", return_value="stamp"
    ):
        deploy_fn.return_value = {"pushed": ["a.txt"], "failed": []}
        apply_fn.return_value = {"sync": {"ok": True}}

        result = run_multi_deploy(mock_db, target_node_ids=[7], sync_after=True, apply_after=False)

    apply_fn.assert_called_once_with(adapter, sync_after=False, apply_after=False)
    adapter.apply_config_changes.assert_not_called()
    assert result["per_node"][0]["status"] == "success"
