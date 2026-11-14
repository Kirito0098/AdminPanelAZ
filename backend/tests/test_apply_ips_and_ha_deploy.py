"""CIDR apply with ``ips`` mode, timeout process cleanup, and HA replication of deploys.

* ``doall.sh ips`` skips the ~100 MB hosts download: CIDR routes never read those lists.
* A timeout must kill the whole doall.sh process tree, not only the leader.
* A nightly/manual deploy to the HA primary must reach the replicas, but replica
  errors are reported as warnings and never fail the primary deploy.
"""

from __future__ import annotations

import logging
import signal
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status

from app.services import background_tasks as background_tasks_module
from app.services.antizapret import AntiZapretService, apply_timeout_seconds
from app.services.cidr.pipeline import orchestrator
from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter
from app.services.node_sync import groups as groups_module
from app.services.node_sync import provider_sync

background_task_service = background_tasks_module.background_task_service


# --- doall.sh invocations ---------------------------------------------------


class _FakeProc:
    def __init__(self, *, returncode: int = 0, output: str = "", timeout: bool = False) -> None:
        self.pid = 4321
        self.returncode = returncode
        self._output = output
        self._timeout = timeout
        self.communicate_calls = 0
        self.killed = False

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        if self._timeout and self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd="doall.sh", timeout=timeout)
        return self._output, ""

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None) -> int:
        return self.returncode


@pytest.fixture
def doall_base(tmp_path: Path) -> Path:
    base = tmp_path / "antizapret"
    base.mkdir()
    (base / "doall.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    return base


def _local_adapter(base: Path) -> LocalNodeAdapter:
    # __new__: the real __init__ builds a CIDR service against the live list dir.
    adapter = LocalNodeAdapter.__new__(LocalNodeAdapter)
    adapter._service = AntiZapretService(base_path=base)
    return adapter


def _patch_popen(monkeypatch, proc: _FakeProc) -> list[tuple[list[str], dict]]:
    calls: list[tuple[list[str], dict]] = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return proc

    monkeypatch.setattr("app.services.antizapret.subprocess.Popen", fake_popen)
    return calls


def test_ips_only_runs_doall_ips(monkeypatch, doall_base):
    adapter = _local_adapter(doall_base)
    calls = _patch_popen(monkeypatch, _FakeProc(output="ips done"))

    assert adapter.apply_config_changes(ips_only=True) == "ips done"

    args, kwargs = calls[-1]
    assert args == [str(doall_base / "doall.sh"), "ips"]
    assert kwargs["start_new_session"] is True


def test_full_apply_runs_doall_without_argument(monkeypatch, doall_base):
    adapter = _local_adapter(doall_base)
    calls = _patch_popen(monkeypatch, _FakeProc(output="full done"))

    assert adapter.apply_config_changes() == "full done"

    args, _kwargs = calls[-1]
    assert args == [str(doall_base / "doall.sh")]


def test_apply_timeout_env_override(monkeypatch):
    monkeypatch.setenv("ANTIZAPRET_APPLY_TIMEOUT_SECONDS", "42")
    assert apply_timeout_seconds() == 42

    monkeypatch.setenv("ANTIZAPRET_APPLY_TIMEOUT_SECONDS", "nonsense")
    assert apply_timeout_seconds() == 300


def test_timeout_kills_whole_process_group(monkeypatch, doall_base):
    monkeypatch.setenv("ANTIZAPRET_APPLY_TIMEOUT_SECONDS", "7")
    adapter = _local_adapter(doall_base)
    proc = _FakeProc(timeout=True)
    _patch_popen(monkeypatch, proc)
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr("app.services.antizapret.os.getpgid", lambda pid: pid * 2)
    monkeypatch.setattr(
        "app.services.antizapret.os.killpg", lambda pgid, sig: killed.append((pgid, sig))
    )

    with pytest.raises(HTTPException) as excinfo:
        adapter.apply_config_changes(ips_only=True)

    assert excinfo.value.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    assert "прервана" in excinfo.value.detail
    assert "7 с" in excinfo.value.detail
    assert killed == [(proc.pid * 2, signal.SIGKILL)]
    assert proc.killed is False


def test_timeout_falls_back_to_proc_kill(monkeypatch, doall_base):
    adapter = _local_adapter(doall_base)
    proc = _FakeProc(timeout=True)
    _patch_popen(monkeypatch, proc)

    def no_group(_pid):
        raise ProcessLookupError("already gone")

    monkeypatch.setattr("app.services.antizapret.os.getpgid", no_group)

    with pytest.raises(HTTPException):
        adapter.apply_config_changes()

    assert proc.killed is True


# --- old agent fallback -----------------------------------------------------


@pytest.mark.parametrize("status_code", [404, 422])
def test_old_agent_falls_back_to_full_doall(monkeypatch, caplog, status_code):
    adapter = RemoteNodeAdapter("127.0.0.1", 9100, "key")
    calls: list[dict] = []

    def fake_request(method, path, *, raw=False, **kwargs):
        calls.append(kwargs)
        if "json" in kwargs:
            raise HTTPException(status_code=status_code, detail="unexpected body")
        return {"detail": "full doall"}

    monkeypatch.setattr(adapter, "_request", fake_request)

    with caplog.at_level(logging.WARNING, logger="app.services.node_adapter"):
        assert adapter.apply_config_changes(ips_only=True) == "full doall"

    assert ["json" in kwargs for kwargs in calls] == [True, False]
    assert any("ips_only" in record.getMessage() for record in caplog.records)


def test_full_apply_does_not_retry_on_agent_error(monkeypatch):
    adapter = RemoteNodeAdapter("127.0.0.1", 9100, "key")
    calls: list[dict] = []

    def fake_request(method, path, *, raw=False, **kwargs):
        calls.append(kwargs)
        raise HTTPException(status_code=422, detail="bad")

    monkeypatch.setattr(adapter, "_request", fake_request)

    with pytest.raises(HTTPException):
        adapter.apply_config_changes()

    assert len(calls) == 1


# --- HA replication of a deploy --------------------------------------------


def _node(node_id: int, name: str) -> MagicMock:
    node = MagicMock()
    node.id = node_id
    node.name = name
    node.openvpn_multihome = False
    return node


@pytest.fixture
def ha_env(monkeypatch):
    primary = _node(1, "primary")
    replica = _node(2, "replica-1")
    group = MagicMock()
    group.id = 10
    group.primary_node_id = primary.id
    adapter = MagicMock(name="primary_adapter")
    adapter.sync_cidr_providers.return_value = {
        "restored": [],
        "sync": {
            "synced_files": 1,
            "updated_files": 0,
            "missing_sources": [],
            "synced": ["AP-1-include-ips.txt"],
            "updated": [],
        },
    }

    monkeypatch.setattr(
        groups_module,
        "find_sync_group_for_primary",
        lambda _db, node_id: group if node_id == primary.id else None,
    )
    monkeypatch.setattr(groups_module, "is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr(groups_module, "get_replica_nodes", lambda _db, _group: [replica])
    replicate = MagicMock(
        return_value={
            "skipped": False,
            "success": True,
            "deploy": {"per_node": []},
            "filenames": ["AP-1-include-ips.txt"],
        }
    )
    monkeypatch.setattr(provider_sync, "deploy_compiled_providers_to_replicas", replicate)
    return SimpleNamespace(
        primary=primary, replica=replica, group=group, adapter=adapter, replicate=replicate
    )


def test_deploy_on_primary_replicates_to_replicas(ha_env):
    db = MagicMock()

    result = orchestrator.run_deploy(
        ha_env.adapter, files=["AP-1-include-ips.txt"], db=db, node=ha_env.primary
    )

    ha_env.replicate.assert_called_once_with(db, ha_env.group, ha_env.adapter)
    assert result["ha_replicas"]["success"] is True


def test_deploy_on_replica_does_not_replicate(ha_env):
    result = orchestrator.run_deploy(ha_env.adapter, db=MagicMock(), node=ha_env.replica)

    ha_env.replicate.assert_not_called()
    assert "ha_replicas" not in result


def test_deploy_without_db_skips_ha_step(ha_env):
    result = orchestrator.run_deploy(ha_env.adapter, files=[])

    ha_env.replicate.assert_not_called()
    assert "ha_replicas" not in result


def test_deploy_skips_replication_when_replicas_already_targeted(ha_env):
    result = orchestrator.run_deploy(
        ha_env.adapter,
        db=MagicMock(),
        node=ha_env.primary,
        deployed_node_ids={ha_env.primary.id, ha_env.replica.id},
    )

    ha_env.replicate.assert_not_called()
    assert "ha_replicas" not in result


def test_replica_error_does_not_fail_deploy(monkeypatch, ha_env):
    ha_env.replicate.side_effect = RuntimeError("SSH-туннель к replica-1 не поднялся")
    monkeypatch.setattr(orchestrator, "resolve_deploy_targets", lambda *_a, **_k: ([ha_env.primary], []))
    monkeypatch.setattr(orchestrator, "get_adapter_for_node", lambda _node: ha_env.adapter)
    monkeypatch.setattr(orchestrator, "maybe_notify_deploy_failed", lambda *_a, **_k: None)

    result = orchestrator.run_multi_deploy(MagicMock(), files=[], apply_after=False)

    assert result["success"] is True
    assert result["nodes_deployed"] == 1
    assert result["per_node"][0]["ha_replicas"]["success"] is False
    assert any("SSH-туннель" in warning for warning in result["warnings"])


def test_partial_replica_failure_is_reported_per_node(monkeypatch, ha_env):
    ha_env.replicate.return_value = {
        "skipped": False,
        "success": False,
        "filenames": ["AP-1-include-ips.txt"],
        "deploy": {
            "per_node": [
                {
                    "node_id": ha_env.replica.id,
                    "node_name": ha_env.replica.name,
                    "status": "failed",
                    "error": "таймаут синхронизации",
                }
            ]
        },
    }
    monkeypatch.setattr(orchestrator, "resolve_deploy_targets", lambda *_a, **_k: ([ha_env.primary], []))
    monkeypatch.setattr(orchestrator, "get_adapter_for_node", lambda _node: ha_env.adapter)
    monkeypatch.setattr(orchestrator, "maybe_notify_deploy_failed", lambda *_a, **_k: None)

    result = orchestrator.run_multi_deploy(MagicMock(), files=[], apply_after=False)

    assert result["success"] is True
    assert result["warnings"] == ["HA-реплика «replica-1»: таймаут синхронизации"]


def test_replicas_in_all_online_target_are_not_deployed_twice(monkeypatch, ha_env):
    monkeypatch.setattr(
        orchestrator,
        "resolve_deploy_targets",
        lambda *_a, **_k: ([ha_env.primary, ha_env.replica], []),
    )
    monkeypatch.setattr(orchestrator, "get_adapter_for_node", lambda _node: ha_env.adapter)
    monkeypatch.setattr(orchestrator, "maybe_notify_deploy_failed", lambda *_a, **_k: None)

    orchestrator.run_multi_deploy(MagicMock(), files=[], all_online=False)

    ha_env.replicate.assert_not_called()


# --- background task wiring -------------------------------------------------


def test_task_routing_apply_uses_ips_only():
    adapter = MagicMock()
    adapter.sync_cidr_providers.return_value = {"restored": []}
    adapter.apply_config_changes.return_value = "doall ok"

    result = background_task_service.task_routing_apply(adapter, recreate_profiles=False)

    adapter.apply_config_changes.assert_called_once_with(ips_only=True)
    assert result["message"] == "Маршрутизация применена (doall.sh)"


def test_task_run_doall_uses_full_apply():
    adapter = MagicMock()
    adapter.apply_config_changes.return_value = "doall ok"

    background_task_service.task_run_doall(adapter, recreate_profiles=False)

    adapter.apply_config_changes.assert_called_once_with(ips_only=False)
