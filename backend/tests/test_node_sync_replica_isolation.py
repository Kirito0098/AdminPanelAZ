"""One unreachable replica must not stop HA replication to the other replicas.

``get_adapter_for_node`` opens the SSH tunnel for ``transport=ssh`` nodes and
raises for a missing API key, so it has to fail per replica like any other call.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models import VpnType
from app.services.node_sync import (
    antizapret_sync,
    client_ops_sync,
    policy_sync,
    provider_sync,
    push_full,
    replicate,
    shared_domain,
    verify,
    vpn_state_sync,
)
from app.services.openvpn_pki import ProfileValidationResult

_DOWN_ERROR = "SSH-туннель к replica-down не поднялся"


def _node(node_id: int, name: str) -> MagicMock:
    node = MagicMock()
    node.id = node_id
    node.name = name
    node.openvpn_multihome = False
    node.openvpn_remote_hosts = None
    return node


def _group(replica_ids: list[int]) -> MagicMock:
    group = MagicMock()
    group.id = 10
    group.primary_node_id = 1
    group.replica_node_ids = replica_ids
    group.sync_mode = "auto"
    group.shared_domain = "vpn.example.com"
    group.shared_domain_wireguard = None
    group.last_verify_result = None
    return group


class _Cluster:
    """Primary 1, unreachable replica 2 listed first, healthy replica 3."""

    def __init__(self) -> None:
        self.primary = _node(1, "primary")
        self.down = _node(2, "replica-down")
        self.up = _node(3, "replica-up")
        self.nodes = {1: self.primary, 2: self.down, 3: self.up}
        self.primary_adapter = MagicMock(name="primary_adapter")
        self.up_adapter = MagicMock(name="up_adapter")
        self.group = _group([2, 3])
        self.db = MagicMock()
        self.db.get.side_effect = lambda _model, node_id: self.nodes.get(node_id)
        self.db.query.return_value.filter.return_value.first.return_value = None

    def adapter_for(self, node):
        if node.id == self.down.id:
            raise RuntimeError(_DOWN_ERROR)
        if node.id == self.primary.id:
            return self.primary_adapter
        return self.up_adapter

    def replicas(self, _db=None, _group=None):
        return [self.down, self.up]


_MODULES = (
    antizapret_sync,
    client_ops_sync,
    policy_sync,
    provider_sync,
    push_full,
    replicate,
    shared_domain,
    verify,
    vpn_state_sync,
)


@pytest.fixture
def cluster(monkeypatch) -> _Cluster:
    import app.services.node_manager as node_manager
    import app.services.node_sync.groups as groups

    c = _Cluster()
    for module in (*_MODULES, node_manager):
        if hasattr(module, "get_adapter_for_node"):
            monkeypatch.setattr(module, "get_adapter_for_node", c.adapter_for)
    for module in (*_MODULES, groups):
        if hasattr(module, "get_replica_nodes"):
            monkeypatch.setattr(module, "get_replica_nodes", c.replicas)
    monkeypatch.setattr(replicate, "_primary_adapter", lambda _db, _group: c.primary_adapter)
    return c


def _error_ids(errors) -> list[int]:
    return [entry["node_id"] for entry in errors]


def _success_ids(successes) -> list[int]:
    return [entry["node_id"] for entry in successes]


def _primary_config(vpn_type: VpnType = VpnType.wireguard) -> MagicMock:
    config = MagicMock()
    config.id = 100
    config.client_name = "alice"
    config.vpn_type = vpn_type
    return config


def _shadow(node_id: int, vpn_type: VpnType) -> MagicMock:
    shadow = MagicMock()
    shadow.node_id = node_id
    shadow.id = 200 + node_id
    shadow.vpn_type = vpn_type
    return shadow


def test_client_create_reaches_healthy_replica(cluster, monkeypatch):
    sync = MagicMock()
    monkeypatch.setattr(replicate, "sync_vpn_crypto_from_primary", sync)

    result = replicate._handle_client_create(cluster.db, cluster.group, {"primary_config": _primary_config()})

    assert _error_ids(result.errors) == [2]
    assert _DOWN_ERROR in result.errors[0]["error"]
    assert _success_ids(result.successes) == [3]
    assert sync.call_args.args[1] is cluster.up_adapter


def test_client_delete_reaches_healthy_replica(cluster, monkeypatch):
    shadows = [_shadow(2, VpnType.wireguard), _shadow(3, VpnType.wireguard)]
    monkeypatch.setattr(replicate, "get_shadow_configs", lambda *_: shadows)
    sync = MagicMock()
    monkeypatch.setattr(replicate, "sync_vpn_crypto_from_primary", sync)

    result = replicate._handle_client_delete(cluster.db, cluster.group, {"primary_config": _primary_config()})

    assert _error_ids(result.errors) == [2]
    assert _success_ids(result.successes) == [3]
    cluster.db.delete.assert_called_once_with(shadows[1])


@pytest.mark.parametrize("with_shadows", [True, False])
def test_client_renew_cert_reaches_healthy_replica(cluster, monkeypatch, with_shadows):
    shadows = [_shadow(2, VpnType.openvpn), _shadow(3, VpnType.openvpn)] if with_shadows else []
    monkeypatch.setattr(replicate, "get_shadow_configs", lambda *_: shadows)
    sync = MagicMock()
    monkeypatch.setattr(replicate, "sync_openvpn_pki_from_primary", sync)

    result = replicate._handle_client_renew_cert(
        cluster.db,
        cluster.group,
        {"primary_config": _primary_config(VpnType.openvpn), "cert_expire_days": 365},
    )

    assert _error_ids(result.errors) == [2]
    assert _success_ids(result.successes) == [3]
    sync.assert_called_once()
    assert sync.call_args.args[1] is cluster.up_adapter


def test_openvpn_disconnect_reaches_healthy_replica(cluster, monkeypatch):
    def disconnect(_db, node, _client, **_kwargs):
        cluster.adapter_for(node)
        return {"success": True}

    apply = MagicMock(side_effect=disconnect)
    monkeypatch.setattr(client_ops_sync, "apply_openvpn_disconnect_on_node", apply)
    monkeypatch.setattr(client_ops_sync, "is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr(client_ops_sync, "finalize_replicate_outcome", MagicMock())

    result = client_ops_sync.replicate_openvpn_disconnect(cluster.db, cluster.group, "alice")

    assert _error_ids(result.errors) == [2]
    assert _success_ids(result.successes) == [3]


def test_primary_crypto_copy_reaches_healthy_replica(cluster, monkeypatch):
    sync = MagicMock()
    monkeypatch.setattr(vpn_state_sync, "sync_vpn_crypto_from_primary", sync)

    result = vpn_state_sync.replicate_primary_crypto_to_replicas(cluster.db, cluster.group, _primary_config())

    assert _error_ids(result["errors"]) == [2]
    assert _success_ids(result["successes"]) == [3]
    assert sync.call_args.args[1] is cluster.up_adapter


def test_policy_op_reaches_healthy_replica(cluster, monkeypatch):
    shadows = [_shadow(2, VpnType.wireguard), _shadow(3, VpnType.wireguard)]
    monkeypatch.setattr(policy_sync, "get_shadow_configs", lambda *_: shadows)
    monkeypatch.setattr(policy_sync, "is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr(
        policy_sync, "get_settings", lambda: MagicMock(node_sync_auto_replicate_policies=True)
    )
    service = MagicMock()
    monkeypatch.setattr(policy_sync, "_policy_service", service)
    monkeypatch.setattr(policy_sync, "_apply_policy_op", MagicMock())
    monkeypatch.setattr(policy_sync, "finalize_replicate_outcome", MagicMock())

    result = policy_sync.replicate_policy_op(cluster.db, cluster.group, _primary_config(), "block_permanent")

    assert _error_ids(result["errors"]) == [2]
    assert _success_ids(result["applied"]) == [3]
    assert service.call_args.args[2] is cluster.up_adapter


def test_antizapret_settings_reach_healthy_replica(cluster, monkeypatch):
    monkeypatch.setattr(antizapret_sync, "is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr(antizapret_sync, "filter_ha_replicable_settings", lambda updates: dict(updates))
    monkeypatch.setattr(antizapret_sync, "finalize_replicate_outcome", MagicMock())

    result = antizapret_sync.replicate_antizapret_settings(cluster.db, cluster.group, {"route_all": "y"})

    assert _error_ids(result.errors) == [2]
    assert _success_ids(result.successes) == [3]
    cluster.up_adapter.update_antizapret_settings.assert_called_once_with({"route_all": "y"})


def test_provider_content_reaches_healthy_replica(cluster, monkeypatch):
    monkeypatch.setattr(provider_sync, "is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr(provider_sync, "finalize_replicate_outcome", MagicMock())

    result = provider_sync.replicate_provider_content(cluster.db, cluster.group, "google.txt", "8.8.8.0/24\n")

    assert _error_ids(result.errors) == [2]
    assert _success_ids(result.successes) == [3]
    cluster.up_adapter.save_provider_content.assert_called_once_with("google.txt", "8.8.8.0/24\n")


def test_verify_reports_unreachable_replica_and_checks_the_rest(cluster, monkeypatch):
    for adapter in (cluster.primary_adapter, cluster.up_adapter):
        adapter.list_openvpn_clients.return_value = ["alice"]
        adapter.list_wireguard_clients.return_value = []
        adapter.get_antizapret_fingerprints.return_value = {}
        adapter.get_config_file_fingerprints.return_value = {}
    monkeypatch.setattr(verify, "_refresh_node_online", lambda _db, _node: True)
    monkeypatch.setattr(
        verify, "validate_all_openvpn_profiles", lambda _adapter: ProfileValidationResult(ready=True, issues=())
    )

    result = verify.verify_sync_group(cluster.db, cluster.group)

    assert result["ready"] is False
    down, up = result["replicas"]
    assert down["node_id"] == 2
    assert down["online"] is False
    assert down["mismatches"][0]["kind"] == "node_status"
    assert _DOWN_ERROR in down["mismatches"][0]["detail"]
    assert up == {"node_id": 3, "node_name": "replica-up", "online": True, "mismatches": []}


def test_shared_domain_apply_continues_after_unreachable_replica(cluster, monkeypatch):
    for adapter in (cluster.primary_adapter, cluster.up_adapter):
        adapter.apply_config_changes.return_value = "doall ok"
        adapter.recreate_profiles.return_value = "recreate ok"
    group = cluster.group
    monkeypatch.setattr(
        shared_domain, "get_member_nodes", lambda _db, _group: [cluster.primary, cluster.down, cluster.up]
    )
    copy_profiles = MagicMock()
    monkeypatch.setattr(shared_domain, "copy_openvpn_profiles_from_primary", copy_profiles)
    monkeypatch.setattr(
        shared_domain,
        "restart_all_openvpn_servers",
        lambda _adapter: {"restarted": [], "failed": [], "skipped": [], "success": True},
    )

    result = shared_domain.apply_shared_domain_to_members(cluster.db, group)

    assert [(e["node_id"], e["stage"]) for e in result["errors"]] == [(2, "setup"), (2, "apply")]
    assert _success_ids(result["applied"]) == [1, 3]
    copy_profiles.assert_called_once_with(cluster.primary_adapter, cluster.up_adapter)


def _push_full_with_replicas(cluster, monkeypatch, replica_order: list[int]):
    cluster.group.replica_node_ids = replica_order
    cluster.primary_adapter.create_antizapret_backup.return_value = {
        "archive_name": "backup.tar.gz",
        "archive_path": "/tmp/backup.tar.gz",
    }
    cluster.primary_adapter.download_antizapret_backup.return_value = b"archive"
    cluster.primary_adapter.get_awg2_health.return_value = {"installed": False}
    extra_up = _node(4, "replica-up-2")
    extra_adapter = MagicMock(name="extra_up_adapter")
    cluster.nodes[4] = extra_up
    base_adapter_for = cluster.adapter_for

    def adapter_for(node):
        return extra_adapter if node.id == 4 else base_adapter_for(node)

    for adapter in (cluster.up_adapter, extra_adapter):
        adapter.restore_antizapret_backup.return_value = {"detail": "ok", "ha_replica": True}
        adapter.apply_wireguard_runtime.return_value = {"success": True}
    admin = MagicMock()
    cluster.db.query.return_value.filter.return_value.first.return_value = admin

    reblock = MagicMock()
    for name, value in {
        "get_adapter_for_node": adapter_for,
        "preflight_push_full_links": lambda _db, _group: [],
        "validate_sync_group_payload": lambda *_a, **_k: [],
        "parse_replica_node_ids": lambda ids: list(ids),
        "read_primary_host_settings": lambda _adapter: {},
        "copy_openvpn_profiles_from_primary": MagicMock(),
        "validate_all_openvpn_profiles": lambda _adapter: ProfileValidationResult(ready=True, issues=()),
        "prune_replica_vpn_clients": lambda *_a: {"success": True, "errors": []},
        "restart_all_openvpn_servers": lambda _adapter: {
            "restarted": [],
            "failed": [],
            "skipped": [],
            "success": True,
        },
        "import_clients_from_disk": MagicMock(),
        "copy_access_policies_from_node": MagicMock(),
        "collect_traffic_snapshot_for_node": MagicMock(),
        "reapply_blocked_runtime_policies": reblock,
        "is_auto_sync_enabled": lambda _group: True,
    }.items():
        monkeypatch.setattr(push_full, name, value)

    result = push_full.run_push_full(cluster.db, cluster.group, auto_verify=False)
    adapters_by_node = {3: cluster.up_adapter, 4: extra_adapter}
    return result, reblock, adapters_by_node


@pytest.mark.parametrize("replica_order", [[2, 3, 4], [3, 2, 4]])
def test_push_full_continues_after_unreachable_replica(cluster, monkeypatch, replica_order):
    result, reblock, adapters_by_node = _push_full_with_replicas(cluster, monkeypatch, replica_order)

    assert sorted(item["node_id"] for item in result["restored"]) == [3, 4]
    assert [(f["node_id"], f["failed_step"]) for f in result["failed"]] == [(2, "restore_replica")]
    assert _DOWN_ERROR in result["failed"][0]["error"]
    assert result["success"] is False
    for call in reblock.call_args_list:
        node, adapter = call.args[1], call.args[2]
        assert adapters_by_node[node.id] is adapter
