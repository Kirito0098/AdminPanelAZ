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
