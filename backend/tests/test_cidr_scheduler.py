"""Unit tests for nightly CIDR scheduler pipeline."""

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.services.cidr.cidr_scheduler import (
    _resolve_cron_deploy_kwargs,
    run_nightly_cidr_pipeline,
)


@pytest.fixture
def mock_db():
    return MagicMock()


def _settings(**overrides) -> Settings:
    base = {
        "cidr_db_compile_after_refresh": False,
        "cidr_db_deploy_after_compile": False,
        "cidr_db_deploy_target": "active",
        "cidr_db_deploy_target_node_ids": "",
    }
    base.update(overrides)
    return Settings(**base)


def test_resolve_cron_deploy_kwargs_active():
    settings = _settings(cidr_db_deploy_target="active")
    assert _resolve_cron_deploy_kwargs(settings) == {}


def test_resolve_cron_deploy_kwargs_all_online():
    settings = _settings(cidr_db_deploy_target="all_online")
    assert _resolve_cron_deploy_kwargs(settings) == {"all_online": True}


def test_resolve_cron_deploy_kwargs_node_ids():
    settings = _settings(
        cidr_db_deploy_target="node_ids",
        cidr_db_deploy_target_node_ids="2, 5",
    )
    assert _resolve_cron_deploy_kwargs(settings) == {"target_node_ids": [2, 5]}


def test_run_nightly_refresh_only(mock_db):
    settings = _settings()
    with patch("app.services.cidr.cidr_scheduler.run_ingest") as ingest_fn:
        ingest_fn.return_value = {
            "status": "ok",
            "providers_updated": 3,
            "providers_failed": 0,
            "log_id": 42,
        }

        result = run_nightly_cidr_pipeline(mock_db, settings)

    ingest_fn.assert_called_once_with(mock_db, triggered_by="cron")
    assert result["refresh"]["log_id"] == 42
    assert result["compile"] is None
    assert result["deploy"] is None


def test_run_nightly_compile_after_refresh(mock_db):
    settings = _settings(cidr_db_compile_after_refresh=True)
    with patch("app.services.cidr.cidr_scheduler.CidrDbUpdaterService") as svc_cls, patch(
        "app.services.cidr.cidr_scheduler.run_ingest"
    ) as ingest_fn, patch(
        "app.services.cidr.cidr_scheduler.run_compile"
    ) as compile_fn, patch(
        "app.services.cidr.cidr_scheduler.compute_artifact_stamp", return_value="abc123"
    ):
        svc = svc_cls.return_value
        ingest_fn.return_value = {
            "status": "ok",
            "providers_updated": 2,
            "providers_failed": 0,
            "log_id": 7,
        }
        compile_fn.return_value = {
            "success": True,
            "updated": ["aws.txt"],
            "failed": [],
            "skipped": [],
            "message": "ok",
        }

        result = run_nightly_cidr_pipeline(mock_db, settings)

    ingest_fn.assert_called_once_with(mock_db, triggered_by="cron")
    compile_fn.assert_called_once_with()
    svc.append_refresh_log_pipeline_details.assert_called_once()
    pipeline_args = svc.append_refresh_log_pipeline_details.call_args[0]
    assert pipeline_args[0] == 7
    assert pipeline_args[1]["artifact_stamp"] == "abc123"
    assert pipeline_args[1]["compile"]["updated"] == ["aws.txt"]
    assert result["compile"]["success"] is True
    assert result["deploy"] is None


def test_run_nightly_deploy_after_compile(mock_db):
    settings = _settings(
        cidr_db_compile_after_refresh=True,
        cidr_db_deploy_after_compile=True,
        cidr_db_deploy_target="all_online",
    )
    with patch("app.services.cidr.cidr_scheduler.CidrDbUpdaterService") as svc_cls, patch(
        "app.services.cidr.cidr_scheduler.run_ingest"
    ) as ingest_fn, patch(
        "app.services.cidr.cidr_scheduler.run_compile"
    ) as compile_fn, patch(
        "app.services.cidr.cidr_scheduler.run_multi_deploy"
    ) as deploy_fn, patch(
        "app.services.cidr.cidr_scheduler.compute_artifact_stamp", return_value="stamp1"
    ):
        svc = svc_cls.return_value
        ingest_fn.return_value = {
            "status": "partial",
            "providers_updated": 1,
            "providers_failed": 1,
            "log_id": 9,
        }
        compile_fn.return_value = {
            "success": True,
            "updated": ["aws.txt", "gcp.txt"],
            "failed": [],
            "skipped": [],
        }
        deploy_fn.return_value = {
            "success": True,
            "artifact_stamp": "stamp1",
            "nodes_deployed": 2,
            "nodes_failed": 0,
            "nodes_skipped": 0,
            "per_node": [],
            "message": "ok",
        }

        result = run_nightly_cidr_pipeline(mock_db, settings)

    deploy_fn.assert_called_once_with(
        mock_db,
        files=["aws.txt", "gcp.txt"],
        sync_after=True,
        apply_after=False,
        all_online=True,
    )
    assert svc.append_refresh_log_pipeline_details.call_count == 2
    deploy_pipeline = svc.append_refresh_log_pipeline_details.call_args_list[1][0][1]
    assert deploy_pipeline["deploy_target"] == "all_online"
    assert deploy_pipeline["deployed_artifact_stamp"] == "stamp1"
    assert result["deploy"]["nodes_deployed"] == 2


def test_run_nightly_skips_compile_on_refresh_error(mock_db):
    settings = _settings(cidr_db_compile_after_refresh=True)
    with patch("app.services.cidr.cidr_scheduler.CidrDbUpdaterService") as svc_cls, patch(
        "app.services.cidr.cidr_scheduler.run_ingest"
    ) as ingest_fn, patch(
        "app.services.cidr.cidr_scheduler.run_compile"
    ) as compile_fn:
        svc = svc_cls.return_value
        ingest_fn.return_value = {
            "status": "error",
            "providers_updated": 0,
            "providers_failed": 5,
            "log_id": 3,
        }

        result = run_nightly_cidr_pipeline(mock_db, settings)

    ingest_fn.assert_called_once_with(mock_db, triggered_by="cron")
    compile_fn.assert_not_called()
    svc.append_refresh_log_pipeline_details.assert_called_once()
    assert result["compile"] is None
