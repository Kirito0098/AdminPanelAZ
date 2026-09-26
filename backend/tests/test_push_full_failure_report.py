"""Push full reports the step and replica where it failed."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models import SyncStatus
from app.services.node_link_errors import link_error_detail
from app.services.node_sync import push_full
from app.services.openvpn_pki import ProfileValidationResult


def _node(node_id: int, name: str) -> MagicMock:
    node = MagicMock()
    node.id = node_id
    node.name = name
    node.openvpn_multihome = False
    return node


def _primary_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.create_antizapret_backup.return_value = {"archive_name": "backup.tar.gz", "archive_path": "/tmp/b.tgz"}
    adapter.download_antizapret_backup.return_value = b"archive-bytes"
    adapter.get_awg2_health.return_value = {"installed": True}
    return adapter


def _replica_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.restore_antizapret_backup.return_value = {"detail": "ok"}
    adapter.apply_wireguard_runtime.return_value = {"success": True}
    return adapter


def _patches(**overrides) -> dict:
    patches = {
        "preflight_push_full_links": MagicMock(return_value=[]),
        "validate_sync_group_payload": MagicMock(return_value=[]),
        "parse_replica_node_ids": MagicMock(return_value=[2, 3]),
        "read_primary_host_settings": MagicMock(return_value={}),
        "copy_openvpn_profiles_from_primary": MagicMock(),
        "validate_all_openvpn_profiles": MagicMock(return_value=ProfileValidationResult(ready=True, issues=())),
        "prune_replica_vpn_clients": MagicMock(return_value={"success": True, "errors": []}),
        "restart_all_openvpn_servers": MagicMock(
            return_value={"restarted": [], "failed": [], "skipped": [], "success": True}
        ),
        "sync_amneziawg2_state_from_primary": MagicMock(),
        "import_clients_from_disk": MagicMock(),
        "copy_access_policies_from_node": MagicMock(),
        "reapply_blocked_runtime_policies": MagicMock(),
        "collect_traffic_snapshot_for_node": MagicMock(),
        "is_auto_sync_enabled": MagicMock(return_value=False),
        "link_primary_configs_to_group": MagicMock(),
    }
    patches.update(overrides)
    return patches


def _run(*, primary_adapter=None, failing_adapter=None, **overrides):
    primary_adapter = primary_adapter or _primary_adapter()
    adapters = {1: primary_adapter, 2: failing_adapter or _replica_adapter(), 3: _replica_adapter()}
    nodes = {1: _node(1, "primary-1"), 2: _node(2, "replica-bad"), 3: _node(3, "replica-ok")}
    group = MagicMock()
    group.id = 10
    group.primary_node_id = 1
    group.replica_node_ids = "[2, 3]"
    group.last_sync_error = None
    db = MagicMock()
    db.get.side_effect = lambda _model, node_id: nodes.get(node_id)
    db.query.return_value.filter.return_value.first.return_value = MagicMock()
    patches = _patches(get_adapter_for_node=MagicMock(side_effect=lambda node: adapters[node.id]), **overrides)
    with ExitStack() as stack:
        for name, value in patches.items():
            stack.enter_context(patch.object(push_full, name, value))
        result = push_full.run_push_full(db, group, auto_verify=False)
    return result, group


def _failing(method: str, error: Exception) -> MagicMock:
    adapter = _replica_adapter()
    getattr(adapter, method).side_effect = error
    return adapter


def _failing_return(method: str, value) -> MagicMock:
    adapter = _replica_adapter()
    getattr(adapter, method).return_value = value
    return adapter


def _only_first_replica(result_ok, failure):
    calls = {"n": 0}

    def fake(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            if isinstance(failure, Exception):
                raise failure
            return failure
        return result_ok

    return MagicMock(side_effect=fake)


_RESTART_OK = {"restarted": [], "failed": [], "skipped": [], "success": True}

_STEP_FAILURES = {
    "restore_replica": lambda: {"failing_adapter": _failing("restore_antizapret_backup", RuntimeError("boom"))},
    "profiles": lambda: {"copy_openvpn_profiles_from_primary": _only_first_replica(None, RuntimeError("boom"))},
    "prune": lambda: {
        "prune_replica_vpn_clients": _only_first_replica(
            {"success": True, "errors": []}, {"success": False, "errors": ["boom"]}
        )
    },
    "restart_openvpn": lambda: {
        "restart_all_openvpn_servers": _only_first_replica(
            _RESTART_OK, {"restarted": [], "failed": [{"unit": "u", "error": "boom"}], "success": False}
        )
    },
    "apply_wireguard": lambda: {
        "failing_adapter": _failing_return("apply_wireguard_runtime", {"success": False, "errors": [{"stderr": "boom"}]})
    },
    "sync_awg2": lambda: {"sync_amneziawg2_state_from_primary": _only_first_replica(None, RuntimeError("boom"))},
    "access_policies": lambda: {"copy_access_policies_from_node": _only_first_replica(None, RuntimeError("boom"))},
    "reblock": lambda: {"reapply_blocked_runtime_policies": _only_first_replica(None, RuntimeError("boom"))},
}


@pytest.mark.parametrize("step", list(_STEP_FAILURES))
def test_failed_replica_records_its_step(step):
    result, group = _run(**_STEP_FAILURES[step]())

    label = push_full.PUSH_FULL_STEP_LABELS[step]
    assert result["success"] is False
    assert result["failed"] == [
        {"node_id": 2, "node_name": "replica-bad", "failed_step": step, "failed_step_label": label, "error": "boom"}
    ]
    assert 3 in [item["node_id"] for item in result["restored"]]
    assert group.sync_status == SyncStatus.failed
    assert group.last_sync_error == f"replica-bad (шаг «{label}»): boom"


def test_every_step_has_a_distinct_label():
    labels = push_full.PUSH_FULL_STEP_LABELS
    assert set(_STEP_FAILURES) | {"backup_primary"} == set(labels)
    assert len(set(labels.values())) == len(labels)


def test_agent_error_detail_is_reported_as_its_message():
    error = HTTPException(status_code=504, detail=link_error_detail("node_timeout", "Таймаут подключения к агенту"))

    result, group = _run(failing_adapter=_failing("restore_antizapret_backup", error))

    assert result["failed"][0]["error"] == "Таймаут подключения к агенту"
    assert group.last_sync_error.endswith("): Таймаут подключения к агенту")


def test_plain_http_error_detail_is_kept():
    result, _ = _run(failing_adapter=_failing("restore_antizapret_backup", HTTPException(500, detail="disk full")))

    assert result["failed"][0]["error"] == "disk full"


@pytest.mark.parametrize("method", ["create_antizapret_backup", "download_antizapret_backup"])
def test_primary_backup_failure_names_the_step_and_primary(method):
    primary_adapter = _primary_adapter()
    getattr(primary_adapter, method).side_effect = HTTPException(
        status_code=502, detail=link_error_detail("node_unreachable", "Узел недоступен: boom")
    )

    with pytest.raises(RuntimeError) as excinfo:
        _run(primary_adapter=primary_adapter)

    assert str(excinfo.value) == "Push full: ошибка на шаге «бэкап primary» (primary-1): Узел недоступен: boom"
    assert isinstance(excinfo.value.__cause__, HTTPException)
