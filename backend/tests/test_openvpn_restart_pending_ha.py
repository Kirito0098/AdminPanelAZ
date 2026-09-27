"""Owed OpenVPN restart on an HA replica (``nodes.openvpn_restart_pending``).

Push full and the shared domain apply restart replica servers after the identity is on
disk, so a successful restart settles the mark; the reconcile check treats a marked
replica as out of sync and heals it through the PKI sync.
"""

from __future__ import annotations

import io
import json
import tarfile
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services import node_manager
from app.services.node_sync import push_full, reconcile_worker, replicate, shared_domain, verify, vpn_state_sync
from app.services.node_sync.openvpn_restart import OPENVPN_SERVER_UNITS
from app.services.openvpn_pki import ProfileValidationResult

_READY = ProfileValidationResult(ready=True, issues=())


def _restart_ok() -> dict:
    return {"success": True, "restarted": list(OPENVPN_SERVER_UNITS), "skipped": [], "failed": []}


def _restart_failed() -> dict:
    return {
        "success": False,
        "restarted": [],
        "skipped": [],
        "failed": [{"unit": OPENVPN_SERVER_UNITS[0], "error": "timeout"}],
    }


@pytest.fixture
def panel_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'panel.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield factory, session
    finally:
        session.close()
        engine.dispose()


def _node(session, name: str, *, pending: bool = False, multihome: bool = False) -> Node:
    node = Node(
        name=name,
        host=f"{name}.example.com",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        node_metadata="{}",
        openvpn_restart_pending=pending,
        openvpn_multihome=multihome,
    )
    session.add(node)
    session.commit()
    return node


def _group(session, primary: Node, replicas: list[Node], *, sync_mode: str = "auto") -> NodeSyncGroup:
    group = NodeSyncGroup(
        name="ha",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=json.dumps([node.id for node in replicas]),
        sync_mode=sync_mode,
        sync_status=SyncStatus.synced,
    )
    session.add(group)
    session.commit()
    return group


def _committed_pending(factory, node_id: int) -> bool:
    with factory() as session:
        return session.get(Node, node_id).openvpn_restart_pending


# --- Push full ---------------------------------------------------------------


def _push_full_primary_adapter() -> MagicMock:
    adapter = MagicMock(name="primary")
    adapter.create_antizapret_backup.return_value = {"archive_name": "backup.tar.gz", "archive_path": "/tmp/b.tar.gz"}
    adapter.download_antizapret_backup.return_value = b"archive-bytes"
    adapter.get_awg2_health.return_value = {"installed": False}
    return adapter


def _push_full_replica_adapter() -> MagicMock:
    adapter = MagicMock(name="replica")
    adapter.restore_antizapret_backup.return_value = {"detail": "ok", "ha_replica": True}
    adapter.apply_wireguard_runtime.return_value = {"success": True}
    return adapter


def _run_push_full(
    db,
    group,
    primary: Node,
    primary_adapter,
    replica_adapter,
    restart: MagicMock,
    ensure=None,
    *,
    auto_verify: bool = False,
):
    ensure = ensure or MagicMock(side_effect=AssertionError("multihome is off"))
    with patch.object(push_full, "preflight_push_full_links", return_value=[]), \
            patch.object(push_full, "validate_sync_group_payload", return_value=[]), \
            patch.object(
                push_full,
                "get_adapter_for_node",
                side_effect=lambda node: primary_adapter if node.id == primary.id else replica_adapter,
            ), \
            patch.object(push_full, "read_primary_host_settings", return_value={}), \
            patch.object(push_full, "copy_openvpn_profiles_from_primary"), \
            patch.object(push_full, "validate_all_openvpn_profiles", return_value=_READY), \
            patch.object(
                push_full,
                "prune_replica_vpn_clients",
                return_value={"success": True, "removed_ovpn": [], "removed_wg": [], "errors": []},
            ), \
            patch.object(push_full, "restart_all_openvpn_servers", restart), \
            patch("app.services.openvpn_multihome.maybe_ensure_node_openvpn_multihome", ensure), \
            patch.object(push_full, "reapply_blocked_runtime_policies"), \
            patch.object(push_full, "link_primary_configs_to_group"), \
            patch.object(push_full, "link_shadow_configs_for_group", return_value=None), \
            patch.object(push_full, "_refresh_group_node_health"):
        return push_full.run_push_full(db, group, auto_verify=auto_verify)


@pytest.mark.parametrize("multihome", [False, True], ids=["plain", "multihome"])
def test_push_full_successful_restart_clears_mark_after_restore(panel_db, multihome):
    factory, db = panel_db
    primary = _node(db, "primary")
    replica = _node(db, "replica", pending=True, multihome=multihome)
    group = _group(db, primary, [replica], sync_mode="manual_full")
    primary_adapter = _push_full_primary_adapter()
    replica_adapter = _push_full_replica_adapter()
    order: list[str] = []
    replica_adapter.restore_antizapret_backup.side_effect = lambda *a, **k: order.append("restore") or {"detail": "ok"}

    def restart_units(_adapter):
        order.append(f"restart pending={_committed_pending(factory, replica.id)}")
        return _restart_ok()

    if multihome:
        restart = MagicMock(side_effect=AssertionError("multihome restarts the servers itself"))
        ensure = MagicMock(side_effect=lambda adapter, _node: {"restart": restart_units(adapter)})
    else:
        restart = MagicMock(side_effect=restart_units)
        ensure = None

    result = _run_push_full(db, group, primary, primary_adapter, replica_adapter, restart, ensure=ensure)

    assert result["success"] is True
    assert order == ["restore", "restart pending=True"]
    assert _committed_pending(factory, replica.id) is False


@pytest.mark.parametrize("failure", ["unsuccessful", "raises"])
def test_push_full_failed_restart_keeps_mark(panel_db, failure):
    factory, db = panel_db
    primary = _node(db, "primary")
    replica = _node(db, "replica", pending=True)
    group = _group(db, primary, [replica], sync_mode="manual_full")
    restart = MagicMock(return_value=_restart_failed())
    if failure == "raises":
        restart.side_effect = RuntimeError("agent unreachable")

    result = _run_push_full(
        db, group, primary, _push_full_primary_adapter(), _push_full_replica_adapter(), restart
    )

    assert result["success"] is False
    assert result["failed"][0]["failed_step"] == "restart_openvpn"
    assert _committed_pending(factory, replica.id) is True


def test_push_full_failed_restore_keeps_mark_and_skips_restart(panel_db):
    factory, db = panel_db
    primary = _node(db, "primary")
    replica = _node(db, "replica", pending=True)
    group = _group(db, primary, [replica], sync_mode="manual_full")
    replica_adapter = _push_full_replica_adapter()
    replica_adapter.restore_antizapret_backup.side_effect = RuntimeError("restore failed")
    restart = MagicMock(return_value=_restart_ok())

    result = _run_push_full(db, group, primary, _push_full_primary_adapter(), replica_adapter, restart)

    assert result["success"] is False
    restart.assert_not_called()
    assert _committed_pending(factory, replica.id) is True


# --- Shared domain -----------------------------------------------------------


def _domain_adapter(name: str) -> MagicMock:
    adapter = MagicMock(name=name)
    adapter.apply_config_changes.return_value = "doall ok"
    adapter.recreate_profiles.return_value = "recreate ok"
    return adapter


def _apply_shared_domain(db, group, adapters: dict[int, MagicMock], restart: MagicMock, copy_profiles=None):
    with patch.object(shared_domain, "get_adapter_for_node", side_effect=lambda node: adapters[node.id]), \
            patch.object(shared_domain, "copy_openvpn_profiles_from_primary", copy_profiles or MagicMock()), \
            patch.object(shared_domain, "patch_openvpn_profiles_on_node"), \
            patch.object(shared_domain, "restart_all_openvpn_servers", restart):
        return shared_domain.apply_shared_domain_to_members(db, group)


def test_shared_domain_clears_mark_only_on_replicas_restarted_successfully(panel_db):
    factory, db = panel_db
    primary = _node(db, "primary", pending=True)
    replica_ok = _node(db, "replica-ok", pending=True)
    replica_failed = _node(db, "replica-failed", pending=True)
    group = _group(db, primary, [replica_ok, replica_failed])
    adapters = {node.id: _domain_adapter(node.name) for node in (primary, replica_ok, replica_failed)}
    failing = adapters[replica_failed.id]
    restart = MagicMock(side_effect=lambda adapter: _restart_failed() if adapter is failing else _restart_ok())

    result = _apply_shared_domain(db, group, adapters, restart)

    assert result["success"] is False
    assert restart.call_count == 3
    assert _committed_pending(factory, replica_ok.id) is False
    assert _committed_pending(factory, replica_failed.id) is True
    assert _committed_pending(factory, primary.id) is True


def test_shared_domain_restart_raising_keeps_mark(panel_db):
    factory, db = panel_db
    primary = _node(db, "primary")
    replica = _node(db, "replica", pending=True)
    group = _group(db, primary, [replica])
    adapters = {node.id: _domain_adapter(node.name) for node in (primary, replica)}
    replica_adapter = adapters[replica.id]

    def restart_units(adapter):
        if adapter is replica_adapter:
            raise RuntimeError("agent unreachable")
        return _restart_ok()

    result = _apply_shared_domain(db, group, adapters, MagicMock(side_effect=restart_units))

    assert result["success"] is False
    assert _committed_pending(factory, replica.id) is True


def test_shared_domain_failure_before_restart_keeps_mark(panel_db):
    factory, db = panel_db
    primary = _node(db, "primary")
    replica = _node(db, "replica", pending=True)
    group = _group(db, primary, [replica])
    adapters = {node.id: _domain_adapter(node.name) for node in (primary, replica)}
    restart = MagicMock(return_value=_restart_ok())

    result = _apply_shared_domain(
        db, group, adapters, restart, copy_profiles=MagicMock(side_effect=RuntimeError("copy failed"))
    )

    assert result["success"] is False
    assert restart.call_count == 1
    assert _committed_pending(factory, replica.id) is True


def test_shared_domain_multihome_restart_clears_mark(panel_db):
    factory, db = panel_db
    primary = _node(db, "primary")
    replica = _node(db, "replica", pending=True, multihome=True)
    group = _group(db, primary, [replica])
    adapters = {node.id: _domain_adapter(node.name) for node in (primary, replica)}
    ensure = MagicMock(return_value={"restart": _restart_ok()})

    with patch("app.services.openvpn_multihome.maybe_ensure_node_openvpn_multihome", ensure):
        result = _apply_shared_domain(db, group, adapters, MagicMock(return_value=_restart_ok()))

    assert result["success"] is True
    ensure.assert_called_once()
    assert _committed_pending(factory, replica.id) is False


# --- Reconcile check -----------------------------------------------------------


def _pki_archive() -> bytes:
    files = {
        "easyrsa3/pki/ca.crt": b"ca",
        "easyrsa3/pki/issued/antizapret-server.crt": b"server-crt",
        "easyrsa3/pki/private/antizapret-server.key": b"server-key",
        "easyrsa3/pki/crl.pem": b"crl",
        "easyrsa3/pki/index.txt": b"V\t360101000000Z\t\t0A\tunknown\t/CN=alice\n",
    }
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _parity_adapter(name: str, archive: bytes) -> MagicMock:
    adapter = MagicMock(name=name)
    adapter.list_openvpn_clients.return_value = ["alice"]
    adapter.list_wireguard_clients.return_value = []
    adapter.get_antizapret_fingerprints.return_value = {"easyrsa3/pki/ca.crt": "ca-hash"}
    adapter.get_config_file_fingerprints.return_value = {}
    adapter.export_easyrsa3_archive.return_value = archive
    adapter.get_awg2_health.return_value = {"installed": False}
    return adapter


@pytest.fixture
def reconcile_env(panel_db, monkeypatch):
    factory, db = panel_db
    primary = _node(db, "primary")
    replica = _node(db, "replica")
    group = _group(db, primary, [replica])
    archive = _pki_archive()
    adapters = {"primary": _parity_adapter("primary", archive), "replica": _parity_adapter("replica", archive)}

    def adapter_for(node):
        return adapters[node.name]

    restart = MagicMock(return_value=_restart_ok())
    heal = MagicMock(wraps=vpn_state_sync.heal_crypto_drift)
    monkeypatch.setattr(reconcile_worker, "SessionLocal", factory)
    monkeypatch.setattr(reconcile_worker, "heal_crypto_drift", heal)
    monkeypatch.setattr(reconcile_worker.settings, "node_sync_auto_heal", True)
    monkeypatch.setattr(reconcile_worker.settings, "node_sync_auto_heal_max_failures", 3)
    monkeypatch.setattr(verify, "_refresh_node_online", lambda _db, node: node is not None)
    monkeypatch.setattr(verify, "get_adapter_for_node", adapter_for)
    monkeypatch.setattr(verify, "validate_all_openvpn_profiles", lambda _adapter: _READY)
    monkeypatch.setattr(node_manager, "get_adapter_for_node", adapter_for)
    monkeypatch.setattr(replicate, "get_adapter_for_node", adapter_for)
    monkeypatch.setattr(vpn_state_sync, "sync_wireguard_state_from_primary", MagicMock())
    monkeypatch.setattr(vpn_state_sync, "copy_openvpn_profiles_from_primary", MagicMock())
    monkeypatch.setattr(vpn_state_sync, "validate_all_openvpn_profiles", lambda _adapter: _READY)
    monkeypatch.setattr(vpn_state_sync, "restart_all_openvpn_servers", restart)
    return {
        "factory": factory,
        "db": db,
        "replica_id": replica.id,
        "group_id": group.id,
        "restart": restart,
        "heal": heal,
        "replica_adapter": adapters["replica"],
    }


def _mark_pending(env) -> None:
    db = env["db"]
    db.get(Node, env["replica_id"]).openvpn_restart_pending = True
    db.commit()


def _group_state(env) -> tuple[SyncStatus, str | None, dict]:
    with env["factory"]() as session:
        group = session.get(NodeSyncGroup, env["group_id"])
        return group.sync_status, group.last_sync_error, json.loads(group.last_verify_result or "{}")


def _replica_mismatch_kinds(verify_result: dict) -> list[str]:
    return [item["kind"] for replica in verify_result.get("replicas") or [] for item in replica["mismatches"]]


def test_verify_reports_replica_with_owed_restart_as_not_ready(reconcile_env):
    _mark_pending(reconcile_env)
    db = reconcile_env["db"]

    result = verify.verify_sync_group(db, db.get(NodeSyncGroup, reconcile_env["group_id"]))

    assert result["ready"] is False
    assert _replica_mismatch_kinds(result) == ["openvpn_restart_pending"]
    assert "перезапущен" in result["replicas"][0]["mismatches"][0]["detail"]


def test_owed_restart_is_healed_by_crypto_sync():
    verify_result = {"replicas": [{"mismatches": [{"kind": "openvpn_restart_pending", "detail": "x"}]}]}

    assert reconcile_worker.classify_heal_actions(verify_result) == ({"crypto_sync"}, False)


def test_reconcile_restarts_replica_with_owed_restart_once(reconcile_env):
    _mark_pending(reconcile_env)

    first = reconcile_worker.reconcile_sync_groups_once()

    assert first["drift"] == []
    reconcile_env["restart"].assert_called_once_with(reconcile_env["replica_adapter"])
    reconcile_env["heal"].assert_called_once()
    assert _committed_pending(reconcile_env["factory"], reconcile_env["replica_id"]) is False
    status, error, verify_result = _group_state(reconcile_env)
    assert (status, error, verify_result["ready"]) == (SyncStatus.synced, None, True)

    second = reconcile_worker.reconcile_sync_groups_once()

    assert second["drift"] == []
    reconcile_env["restart"].assert_called_once()
    reconcile_env["heal"].assert_called_once()


def test_reconcile_failed_restart_keeps_mark_and_reports_drift(reconcile_env):
    _mark_pending(reconcile_env)
    reconcile_env["restart"].return_value = _restart_failed()

    result = reconcile_worker.reconcile_sync_groups_once()

    reconcile_env["restart"].assert_called_once()
    assert _committed_pending(reconcile_env["factory"], reconcile_env["replica_id"]) is True
    assert [item["auto_heal_failures"] for item in result["drift"]] == [1]
    status, error, verify_result = _group_state(reconcile_env)
    assert status == SyncStatus.failed
    assert "timeout" in error
    assert _replica_mismatch_kinds(verify_result) == ["openvpn_restart_pending"]


def test_reconcile_without_mark_does_not_heal_or_restart(reconcile_env):
    result = reconcile_worker.reconcile_sync_groups_once()

    assert (result["checked"], result["drift"]) == (1, [])
    reconcile_env["heal"].assert_not_called()
    reconcile_env["restart"].assert_not_called()
    status, error, verify_result = _group_state(reconcile_env)
    assert (status, error, verify_result["ready"]) == (SyncStatus.synced, None, True)


@pytest.mark.parametrize(
    "pause_answers",
    [pytest.param([True], id="before-verify"), pytest.param([False, True], id="before-heal")],
)
def test_reconcile_does_not_heal_while_background_pause_is_requested(reconcile_env, monkeypatch, pause_answers):
    _mark_pending(reconcile_env)
    answers = iter(pause_answers)
    monkeypatch.setattr(reconcile_worker, "background_pause_requested", lambda: next(answers, True))

    reconcile_worker.reconcile_sync_groups_once()

    reconcile_env["heal"].assert_not_called()
    reconcile_env["restart"].assert_not_called()
    assert _committed_pending(reconcile_env["factory"], reconcile_env["replica_id"]) is True


# --- Auto-heal suspension after repeated failures --------------------------------


def _set_heal_failures(env, count: int) -> None:
    db = env["db"]
    group = db.get(NodeSyncGroup, env["group_id"])
    group.last_verify_result = json.dumps({"ready": False, "auto_heal_failures": count})
    db.commit()


def test_reconcile_skips_auto_heal_after_max_failures_but_keeps_checking(reconcile_env):
    _mark_pending(reconcile_env)
    _set_heal_failures(reconcile_env, 3)

    result = reconcile_worker.reconcile_sync_groups_once()

    reconcile_env["heal"].assert_not_called()
    reconcile_env["restart"].assert_not_called()
    assert result["checked"] == 1
    assert [(item["auto_heal_failures"], item["notify"]) for item in result["drift"]] == [(3, False)]
    status, error, verify_result = _group_state(reconcile_env)
    assert status == SyncStatus.failed
    assert "Автолечение приостановлено после 3 неудачных попыток подряд" in error
    assert "«Синхронизировать»" in error
    assert verify_result["auto_heal_failures"] == 3
    assert _replica_mismatch_kinds(verify_result) == ["openvpn_restart_pending"]


@pytest.mark.parametrize("prior_failures", [0, 1])
def test_reconcile_heals_below_max_failures(reconcile_env, prior_failures):
    _mark_pending(reconcile_env)
    _set_heal_failures(reconcile_env, prior_failures)
    reconcile_env["restart"].return_value = _restart_failed()

    result = reconcile_worker.reconcile_sync_groups_once()

    reconcile_env["heal"].assert_called_once()
    reconcile_env["restart"].assert_called_once()
    assert [(item["auto_heal_failures"], item["notify"]) for item in result["drift"]] == [
        (prior_failures + 1, False)
    ]
    _, error, _ = _group_state(reconcile_env)
    assert error.startswith(f"auto-heal attempt {prior_failures + 1}/3:")
    assert "приостановлено" not in error


def test_reconcile_attempt_reaching_max_failures_reports_suspension(reconcile_env):
    _mark_pending(reconcile_env)
    _set_heal_failures(reconcile_env, 2)
    reconcile_env["restart"].return_value = _restart_failed()

    result = reconcile_worker.reconcile_sync_groups_once()

    reconcile_env["restart"].assert_called_once()
    assert [(item["auto_heal_failures"], item["notify"]) for item in result["drift"]] == [(3, True)]
    assert "приостановлено" in result["drift"][0]["hint"]
    _, error, _ = _group_state(reconcile_env)
    assert "Автолечение приостановлено после 3 неудачных попыток подряд" in error
    assert "timeout" in error


def test_successful_push_full_resets_failures_and_resumes_auto_heal(reconcile_env):
    _mark_pending(reconcile_env)
    _set_heal_failures(reconcile_env, 3)
    reconcile_worker.reconcile_sync_groups_once()
    reconcile_env["heal"].assert_not_called()

    db = reconcile_env["db"]
    db.expire_all()
    group = db.get(NodeSyncGroup, reconcile_env["group_id"])
    primary = db.get(Node, group.primary_node_id)
    push_result = _run_push_full(
        db,
        group,
        primary,
        _push_full_primary_adapter(),
        _push_full_replica_adapter(),
        MagicMock(return_value=_restart_ok()),
        auto_verify=True,
    )

    assert push_result["success"] is True
    status, error, verify_result = _group_state(reconcile_env)
    assert (status, error, verify_result["ready"]) == (SyncStatus.synced, None, True)
    assert verify_result.get("auto_heal_failures", 0) == 0

    _mark_pending(reconcile_env)
    result = reconcile_worker.reconcile_sync_groups_once()

    assert result["drift"] == []
    reconcile_env["heal"].assert_called_once()
    reconcile_env["restart"].assert_called_once()


@pytest.mark.parametrize("check", ["reconcile", "manual"])
def test_ready_check_resets_failures_and_resumes_auto_heal(reconcile_env, check):
    _set_heal_failures(reconcile_env, 3)
    db = reconcile_env["db"]

    if check == "reconcile":
        assert reconcile_worker.reconcile_sync_groups_once()["drift"] == []
    else:
        verify.verify_sync_group(db, db.get(NodeSyncGroup, reconcile_env["group_id"]))

    _, _, verify_result = _group_state(reconcile_env)
    assert verify_result["ready"] is True
    assert verify_result.get("auto_heal_failures", 0) == 0

    _mark_pending(reconcile_env)
    reconcile_worker.reconcile_sync_groups_once()

    reconcile_env["heal"].assert_called_once()
    reconcile_env["restart"].assert_called_once()


def test_check_with_offline_primary_keeps_failures(reconcile_env, monkeypatch):
    _set_heal_failures(reconcile_env, 3)
    monkeypatch.setattr(verify, "_refresh_node_online", lambda _db, _node: False)
    db = reconcile_env["db"]

    result = verify.verify_sync_group(db, db.get(NodeSyncGroup, reconcile_env["group_id"]))

    assert result["ready"] is False
    assert _group_state(reconcile_env)[2]["auto_heal_failures"] == 3


def test_auto_heal_suspension_is_notified_once(reconcile_env, monkeypatch):
    _mark_pending(reconcile_env)
    reconcile_env["restart"].return_value = _restart_failed()
    monkeypatch.setattr(reconcile_worker.settings, "node_sync_auto_heal_max_failures", 2)
    notify = MagicMock()
    monkeypatch.setattr(reconcile_worker, "_notify_drift", notify)

    for _ in range(5):
        reconcile_worker.reconcile_sync_groups_safe()

    assert reconcile_env["restart"].call_count == 2
    notify.assert_called_once()
    (items,), _ = notify.call_args
    assert [item["auto_heal_failures"] for item in items] == [2]
    assert "приостановлено после 2" in items[0]["hint"]
    assert _group_state(reconcile_env)[2]["auto_heal_failures"] == 2


def test_group_warning_reports_suspended_auto_heal(reconcile_env, monkeypatch):
    from app.config import get_settings
    from app.services.node_sync.groups import build_group_warnings

    monkeypatch.setattr(get_settings(), "node_sync_auto_heal", True)
    monkeypatch.setattr(get_settings(), "node_sync_auto_heal_max_failures", 3)
    group = reconcile_env["db"].get(NodeSyncGroup, reconcile_env["group_id"])

    below = build_group_warnings(group, {"ready": False, "auto_heal_failures": 2})
    suspended = build_group_warnings(group, {"ready": False, "auto_heal_failures": 3})

    assert below == ["Auto-heal: 2 неудачных попыток"]
    assert len(suspended) == 1
    assert "Автолечение приостановлено после 3 неудачных попыток подряд" in suspended[0]
    assert "«Синхронизировать»" in suspended[0]
