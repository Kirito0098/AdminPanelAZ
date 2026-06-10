"""Unit tests for CIDR artifact deploy (push to remote nodes)."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.cidr.pipeline.deploy import list_compile_artifacts, push_cidr_artifacts
from app.services.cidr.pipeline.orchestrator import run_deploy
from app.services.node_adapter import RemoteNodeAdapter


@pytest.fixture
def list_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.cidr.pipeline.deploy.LIST_DIR", str(tmp_path))
    return tmp_path


def test_list_compile_artifacts_counts_non_comment_lines(list_dir):
    (list_dir / "aws.txt").write_text(
        "# header\n10.0.0.0/8\n172.16.0.0/12\n",
        encoding="utf-8",
    )
    (list_dir / "_baseline").mkdir()
    (list_dir / "_baseline" / "aws.txt").write_text("ignored\n", encoding="utf-8")

    artifacts = list_compile_artifacts()

    assert artifacts == {"aws.txt": {"cidr_count": 2, "exists": True}}


def test_push_cidr_artifacts_calls_save_for_each_file(list_dir):
    (list_dir / "aws.txt").write_text("10.0.0.0/8\n", encoding="utf-8")
    (list_dir / "google.txt").write_text("172.16.0.0/12\n", encoding="utf-8")

    adapter = MagicMock()
    adapter.save_provider_content.return_value = {"success": True}

    result = push_cidr_artifacts(adapter, filenames=["aws.txt", "google.txt"])

    assert adapter.save_provider_content.call_count == 2
    adapter.save_provider_content.assert_any_call("aws.txt", "10.0.0.0/8\n")
    adapter.save_provider_content.assert_any_call("google.txt", "172.16.0.0/12\n")
    assert result["pushed"] == ["aws.txt", "google.txt"]
    assert result["failed"] == []
    assert result["skipped"] == []


def test_push_cidr_artifacts_reads_all_txt_when_filenames_omitted(list_dir):
    (list_dir / "aws.txt").write_text("10.0.0.0/8\n", encoding="utf-8")
    (list_dir / "google.txt").write_text("172.16.0.0/12\n", encoding="utf-8")
    (list_dir / "_baseline").mkdir()

    adapter = MagicMock()

    result = push_cidr_artifacts(adapter)

    assert adapter.save_provider_content.call_count == 2
    assert set(result["pushed"]) == {"aws.txt", "google.txt"}


def test_push_cidr_artifacts_accepts_compile_updated_shape(list_dir):
    (list_dir / "aws.txt").write_text("10.0.0.0/8\n", encoding="utf-8")

    adapter = MagicMock()
    updated = [{"file": "aws.txt", "cidr_count": 1, "source": "db"}]

    result = push_cidr_artifacts(adapter, filenames=updated)

    adapter.save_provider_content.assert_called_once_with("aws.txt", "10.0.0.0/8\n")
    assert result["pushed"] == ["aws.txt"]


def test_push_cidr_artifacts_records_missing_and_failed_files(list_dir):
    adapter = MagicMock()
    adapter.save_provider_content.side_effect = [
        {"success": True},
        RuntimeError("connection refused"),
    ]
    (list_dir / "aws.txt").write_text("10.0.0.0/8\n", encoding="utf-8")
    (list_dir / "google.txt").write_text("172.16.0.0/12\n", encoding="utf-8")

    result = push_cidr_artifacts(adapter, filenames=["missing.txt", "aws.txt", "google.txt"])

    assert result["skipped"] == ["missing.txt"]
    assert result["pushed"] == ["aws.txt"]
    assert len(result["failed"]) == 1
    assert result["failed"][0]["file"] == "google.txt"


def test_run_deploy_remote_pushes_then_syncs(list_dir):
    (list_dir / "aws.txt").write_text("10.0.0.0/8\n", encoding="utf-8")

    adapter = RemoteNodeAdapter("10.0.0.1", 8443, "secret-key")
    with patch.object(adapter, "save_provider_content", return_value={"success": True}) as save_fn, patch.object(
        adapter, "sync_cidr_providers", return_value={"changed": 1}
    ) as sync_fn:
        result = run_deploy(adapter, files=["aws.txt"])

    save_fn.assert_called_once_with("aws.txt", "10.0.0.0/8\n")
    sync_fn.assert_called_once()
    assert result["mode"] == "remote"
    assert result["pushed"] == ["aws.txt"]
    assert result["failed"] == []
    assert result["sync"] == {"changed": 1}
