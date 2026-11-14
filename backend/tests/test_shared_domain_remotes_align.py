"""Domain apply must leave shared_domain in remotes so client.sh 7 is not undone."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.node_sync import shared_domain
from app.services.openvpn_remote_hosts import align_remote_hosts_to_domain, hosts_to_json, parse_hosts_json


def test_align_remote_hosts_replaces_list_with_domain_only():
    assert align_remote_hosts_to_domain("vpn.example.com", []) == ["vpn.example.com"]
    assert align_remote_hosts_to_domain(
        "vpn.example.com",
        ["198.51.100.7", "vpn.example.com", "backup.example.com"],
    ) == ["vpn.example.com"]
    assert align_remote_hosts_to_domain("", ["keep.me"]) == []


def test_shared_domain_apply_drops_foreign_remotes_before_patch(monkeypatch):
    primary = MagicMock()
    primary.id = 1
    primary.name = "ha2-primary"
    primary.openvpn_multihome = False
    # Polluted by proxy remotes from another HA group
    primary.openvpn_remote_hosts = hosts_to_json(
        ["ru-proxy.mtdrx.online", "vpn.mtdrx.online", "net-2.cloakweb.ru"]
    )
    primary.openvpn_restart_pending = False

    group = MagicMock()
    group.primary_node_id = 1
    group.replica_node_ids = []
    group.shared_domain = "net-2.cloakweb.ru"
    group.shared_domain_wireguard = None

    adapter = MagicMock()
    adapter.apply_config_changes.return_value = "doall ok"
    adapter.recreate_profiles.return_value = "recreate ok"
    patched: list[list[str]] = []

    monkeypatch.setattr(shared_domain, "get_member_nodes", lambda _db, _group: [primary])
    monkeypatch.setattr(shared_domain, "get_adapter_for_node", lambda _node: adapter)
    monkeypatch.setattr(
        shared_domain,
        "patch_openvpn_profiles_on_node",
        lambda _adapter, hosts: patched.append(list(hosts)) or {"patched": 1, "warnings": []},
    )
    monkeypatch.setattr(
        shared_domain,
        "restart_all_openvpn_servers",
        lambda _adapter: {"restarted": [], "failed": [], "skipped": [], "success": True},
    )

    db = MagicMock()
    result = shared_domain.apply_shared_domain_to_members(db, group)

    assert result["success"] is True
    adapter.recreate_profiles.assert_called_once()
    assert patched == [["net-2.cloakweb.ru"]]
    assert parse_hosts_json(primary.openvpn_remote_hosts) == ["net-2.cloakweb.ru"]
    db.commit.assert_called()


def test_apply_replicas_false_skips_replica_apply(monkeypatch):
    primary = MagicMock()
    primary.id = 1
    primary.name = "primary"
    primary.openvpn_multihome = False
    primary.openvpn_remote_hosts = hosts_to_json(["vpn.example.com"])
    primary.openvpn_restart_pending = False

    replica = MagicMock()
    replica.id = 2
    replica.name = "replica"
    replica.openvpn_multihome = False
    replica.openvpn_remote_hosts = hosts_to_json(["vpn.example.com"])
    replica.openvpn_restart_pending = False

    group = MagicMock()
    group.primary_node_id = 1
    group.replica_node_ids = [2]
    group.shared_domain = "vpn.example.com"
    group.shared_domain_wireguard = None

    primary_adapter = MagicMock()
    primary_adapter.apply_config_changes.return_value = "doall ok"
    primary_adapter.recreate_profiles.return_value = "recreate ok"
    replica_adapter = MagicMock()
    replica_adapter.apply_config_changes.return_value = "doall ok"
    replica_adapter.recreate_profiles.return_value = "recreate ok"
    adapters = {1: primary_adapter, 2: replica_adapter}

    monkeypatch.setattr(shared_domain, "get_member_nodes", lambda _db, _group: [primary, replica])
    monkeypatch.setattr(shared_domain, "get_adapter_for_node", lambda node: adapters[node.id])
    monkeypatch.setattr(
        shared_domain,
        "patch_openvpn_profiles_on_node",
        lambda _adapter, hosts: {"patched": 1, "warnings": []},
    )
    monkeypatch.setattr(
        shared_domain,
        "restart_all_openvpn_servers",
        lambda _adapter: {"restarted": [], "failed": [], "skipped": [], "success": True},
    )

    db = MagicMock()
    result = shared_domain.apply_shared_domain_to_members(
        db, group, run_apply=True, apply_replicas=False
    )

    assert result["success"] is True
    primary_adapter.apply_config_changes.assert_called_once()
    primary_adapter.recreate_profiles.assert_called_once()
    replica_adapter.apply_config_changes.assert_not_called()
    replica_adapter.recreate_profiles.assert_not_called()
    # setup-запись и выравнивание remotes всё равно идут на обоих узлах.
    replica_adapter.update_antizapret_settings.assert_called_once()
