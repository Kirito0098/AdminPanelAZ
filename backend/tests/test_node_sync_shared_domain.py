"""Shared domain apply: replicas must get byte-copied .ovpn from primary."""

from unittest.mock import MagicMock, patch

from app.services.node_sync import shared_domain


def _make_node(node_id: int, name: str) -> MagicMock:
    node = MagicMock()
    node.id = node_id
    node.name = name
    return node


def _make_group(*, primary_id: int = 1, domain: str = "vpn.example.com") -> MagicMock:
    group = MagicMock()
    group.id = 10
    group.primary_node_id = primary_id
    group.replica_node_ids = [2]
    group.shared_domain = domain
    return group


def _adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.apply_config_changes.return_value = "doall ok"
    adapter.recreate_profiles.return_value = "recreate ok"
    return adapter


def test_apply_shared_domain_copies_ovpn_from_primary_to_replica():
    group = _make_group()
    primary = _make_node(1, "primary")
    replica = _make_node(2, "replica")
    db = MagicMock()

    primary_adapter = _adapter()
    replica_adapter = _adapter()
    adapters = {1: primary_adapter, 2: replica_adapter}

    copy_mock = MagicMock()
    with patch.object(shared_domain, "get_member_nodes", return_value=[primary, replica]):
        with patch.object(
            shared_domain, "get_adapter_for_node", side_effect=lambda node: adapters[node.id]
        ):
            with patch.object(shared_domain, "copy_openvpn_profiles_from_primary", copy_mock):
                with patch.object(
                    shared_domain,
                    "restart_all_openvpn_servers",
                    return_value={"restarted": [], "failed": [], "skipped": [], "success": True},
                ):
                    result = shared_domain.apply_shared_domain_to_members(db, group)

    assert result["success"] is True
    # client.sh 7 ran on both nodes (hosts must land in profiles)
    primary_adapter.recreate_profiles.assert_called_once()
    replica_adapter.recreate_profiles.assert_called_once()
    # but replica .ovpn got replaced with a byte-copy from primary
    copy_mock.assert_called_once_with(primary_adapter, replica_adapter)


def test_apply_shared_domain_skips_copy_and_records_error_when_primary_apply_failed():
    group = _make_group()
    primary = _make_node(1, "primary")
    replica = _make_node(2, "replica")
    db = MagicMock()

    primary_adapter = _adapter()
    primary_adapter.apply_config_changes.side_effect = RuntimeError("doall failed")
    replica_adapter = _adapter()
    adapters = {1: primary_adapter, 2: replica_adapter}

    copy_mock = MagicMock()
    with patch.object(shared_domain, "get_member_nodes", return_value=[primary, replica]):
        with patch.object(
            shared_domain, "get_adapter_for_node", side_effect=lambda node: adapters[node.id]
        ):
            with patch.object(shared_domain, "copy_openvpn_profiles_from_primary", copy_mock):
                with patch.object(
                    shared_domain,
                    "restart_all_openvpn_servers",
                    return_value={"restarted": [], "failed": [], "skipped": [], "success": True},
                ):
                    result = shared_domain.apply_shared_domain_to_members(db, group)

    assert result["success"] is False
    copy_mock.assert_not_called()
    stages = {item.get("stage") for item in result["errors"]}
    assert "profile_copy" in stages


def test_apply_shared_domain_records_error_when_copy_fails():
    group = _make_group()
    primary = _make_node(1, "primary")
    replica = _make_node(2, "replica")
    db = MagicMock()

    primary_adapter = _adapter()
    replica_adapter = _adapter()
    adapters = {1: primary_adapter, 2: replica_adapter}

    copy_mock = MagicMock(side_effect=RuntimeError("copy failed"))
    with patch.object(shared_domain, "get_member_nodes", return_value=[primary, replica]):
        with patch.object(
            shared_domain, "get_adapter_for_node", side_effect=lambda node: adapters[node.id]
        ):
            with patch.object(shared_domain, "copy_openvpn_profiles_from_primary", copy_mock):
                with patch.object(
                    shared_domain,
                    "restart_all_openvpn_servers",
                    return_value={"restarted": [], "failed": [], "skipped": [], "success": True},
                ):
                    result = shared_domain.apply_shared_domain_to_members(db, group)

    assert result["success"] is False
    assert any("copy failed" in str(item.get("error")) for item in result["errors"])
