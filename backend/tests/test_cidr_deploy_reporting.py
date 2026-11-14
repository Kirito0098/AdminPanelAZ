"""Deploy reporting must show the real volume, not only changed files.

The panel can run on the VPN node itself: then ``LocalNodeAdapter`` only syncs
LIST_DIR → AntiZapret config and pushes nothing. Reporting ``pushed`` alone showed
«Файлов 0» for a deploy that actually synced six files, so the local branch reports
``synced`` (volume) next to ``pushed`` (real changes).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.cidr.ip_manager import IpManager
from app.services.cidr.pipeline import orchestrator
from app.services.node_adapter import RemoteNodeAdapter

PROVIDER_A = "akamai-ips.txt"
PROVIDER_B = "amazon-ips.txt"

LOCAL_SYNC = {
    "restored": {},
    "sync": {
        "synced_files": 2,
        "updated_files": 1,
        "missing_sources": [],
        "synced": [PROVIDER_A, PROVIDER_B],
        "updated": [PROVIDER_B],
    },
}


class LocalStub:
    """Panel on the VPN node: local adapter has no artifact push, only sync."""

    def __init__(self, sync_result: dict):
        self.sync_result = sync_result

    def sync_cidr_providers(self) -> dict:
        return self.sync_result


class RemoteStub(RemoteNodeAdapter):
    """Remote adapter without HTTP wiring: only the branch selection matters here."""

    def __init__(self, sync_result: dict):
        self.sync_result = sync_result
        self.base_url = "https://node.invalid:8765"

    def sync_cidr_providers(self) -> dict:
        return self.sync_result


def _node(node_id: int = 1, name: str = "Germani") -> MagicMock:
    node = MagicMock()
    node.id = node_id
    node.name = name
    node.openvpn_multihome = False
    return node


def _run_multi(monkeypatch, adapter, node, **kwargs) -> dict:
    monkeypatch.setattr(orchestrator, "resolve_deploy_targets", lambda *_a, **_k: ([node], []))
    monkeypatch.setattr(orchestrator, "get_adapter_for_node", lambda _node: adapter)
    monkeypatch.setattr(orchestrator, "maybe_notify_deploy_failed", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator, "compute_artifact_stamp", lambda: "stamp-1")
    return orchestrator.run_multi_deploy(
        MagicMock(), sync_after=False, apply_after=False, **kwargs
    )


def test_local_deploy_reports_synced_volume_and_real_changes(monkeypatch):
    adapter = LocalStub(LOCAL_SYNC)

    deploy = orchestrator.run_deploy(adapter)

    assert deploy["mode"] == "local"
    assert deploy["pushed"] == [PROVIDER_B]
    assert deploy["synced"] == [PROVIDER_A, PROVIDER_B]
    assert deploy["skipped"] == []

    result = _run_multi(monkeypatch, adapter, _node())
    entry = result["per_node"][0]

    assert entry["status"] == "success"
    assert entry["synced_files"] == [PROVIDER_A, PROVIDER_B]
    assert entry["updated_files"] == [PROVIDER_B]
    assert entry["noop"] is False
    assert result["success"] is True
    assert result["nodes_deployed"] == 1
    assert result["message"] == "Развёрнуто на 1 узел(ов), файлов: 2 (изменено 1)"


def test_local_deploy_without_changes_is_a_noop_success(monkeypatch):
    adapter = LocalStub(
        {
            "restored": {},
            "sync": {
                "synced_files": 2,
                "updated_files": 0,
                "missing_sources": [],
                "synced": [PROVIDER_A, PROVIDER_B],
                "updated": [],
            },
        }
    )

    result = _run_multi(monkeypatch, adapter, _node())
    entry = result["per_node"][0]

    assert entry["status"] == "success"
    assert entry["noop"] is True
    assert entry["synced_files"] == [PROVIDER_A, PROVIDER_B]
    assert entry["updated_files"] == []
    assert result["success"] is True
    assert result["noop"] is True
    assert result["message"] == "Развёрнуто на 1 узел(ов): файлов 2, изменений нет"


def test_local_deploy_without_compiled_files_is_skipped_not_success(monkeypatch):
    adapter = LocalStub(
        {
            "restored": {},
            "sync": {
                "synced_files": 0,
                "updated_files": 0,
                "missing_sources": [PROVIDER_A],
                "synced": [],
                "updated": [],
            },
        }
    )

    result = _run_multi(monkeypatch, adapter, _node())
    entry = result["per_node"][0]

    assert entry["status"] == "skipped"
    assert "Нечего разворачивать" in entry["error"]
    assert result["success"] is False
    assert result["nodes_skipped"] == 1
    assert result["message"] == (
        "Нечего разворачивать: файлы не собраны (выполните сборку — этап 2)"
    )


def test_remote_deploy_still_reports_pushed_artifacts(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "push_cidr_artifacts",
        lambda _adapter, filenames=None: {
            "pushed": [PROVIDER_A, PROVIDER_B],
            "failed": [],
            "skipped": [],
        },
    )
    adapter = RemoteStub({"restored": {}, "sync": {"synced_files": 2}})

    deploy = orchestrator.run_deploy(adapter, files=[PROVIDER_A, PROVIDER_B])

    assert deploy["mode"] == "remote"
    assert deploy["pushed"] == [PROVIDER_A, PROVIDER_B]
    assert "synced" not in deploy

    result = _run_multi(monkeypatch, adapter, _node(), files=[PROVIDER_A, PROVIDER_B])
    entry = result["per_node"][0]

    assert entry["status"] == "success"
    assert entry["updated_files"] == [PROVIDER_A, PROVIDER_B]
    assert result["success"] is True
    assert result["message"] == "Развёрнуто на 1 узел(ов), файлов: 2 (изменено 2)"


@pytest.fixture
def manager(tmp_path):
    list_dir = tmp_path / "list"
    config_dir = tmp_path / "antizapret" / "config"
    list_dir.mkdir()
    config_dir.mkdir(parents=True)
    return IpManager(list_dir, config_dir)


def _write(path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_sync_enabled_from_list_returns_file_names(manager):
    _write(manager.list_dir / PROVIDER_A, "1.1.1.0/24\n")
    _write(manager.list_dir / PROVIDER_B, "8.8.8.0/24\n")
    manager.enable_file(PROVIDER_A)
    manager.enable_file(PROVIDER_B)
    _write(manager.list_dir / PROVIDER_B, "8.8.8.0/24\n9.9.9.0/24\n")

    result = manager.sync_enabled_from_list()

    assert result["synced"] == [PROVIDER_A, PROVIDER_B]
    assert result["updated"] == [PROVIDER_B]
    assert result["synced_files"] == 2
    assert result["updated_files"] == 1
    assert result["missing_sources"] == []
