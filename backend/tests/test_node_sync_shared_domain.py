"""Propagate Sync Group shared_domain to setup hosts + doall.sh + client.sh 7."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.node_sync.groups import serialize_replica_node_ids
from app.services.node_sync.shared_domain import apply_shared_domain_to_members


@pytest.fixture()
def group_db(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online)
    replica = Node(name="replica", host="10.0.0.2", port=9100, status=NodeStatus.online)
    db_session.add_all([primary, replica])
    db_session.commit()
    group = NodeSyncGroup(
        name="HA",
        shared_domain="azxs123.duckdns.org",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_mode="manual_full",
        sync_status=SyncStatus.unknown,
    )
    db_session.add(group)
    db_session.commit()
    return db_session, group, primary, replica


def test_writes_hosts_then_doall_and_recreate_on_every_member(group_db):
    db, group, primary, replica = group_db
    adapters: dict[int, MagicMock] = {primary.id: MagicMock(), replica.id: MagicMock()}

    with patch(
        "app.services.node_sync.shared_domain.get_adapter_for_node",
        side_effect=lambda node: adapters[node.id],
    ):
        result = apply_shared_domain_to_members(db, group, run_apply=True)

    assert result["success"] is True
    assert result["domain"] == "azxs123.duckdns.org"
    assert {item["node_id"] for item in result["updated"]} == {primary.id, replica.id}
    assert {item["node_id"] for item in result["applied"]} == {primary.id, replica.id}

    for adapter in adapters.values():
        adapter.update_antizapret_settings.assert_called_once_with(
            {"openvpn_host": "azxs123.duckdns.org", "wireguard_host": "azxs123.duckdns.org"}
        )
        adapter.apply_config_changes.assert_called_once()
        adapter.recreate_profiles.assert_called_once()


def test_run_apply_false_skips_doall_and_recreate(group_db):
    db, group, primary, replica = group_db
    adapter = MagicMock()

    with patch(
        "app.services.node_sync.shared_domain.get_adapter_for_node",
        return_value=adapter,
    ):
        result = apply_shared_domain_to_members(db, group, run_apply=False)

    assert result["success"] is True
    assert result["applied"] == []
    assert adapter.apply_config_changes.call_count == 0
    assert adapter.recreate_profiles.call_count == 0
    assert adapter.update_antizapret_settings.call_count == 2


def test_partial_failure_records_error_and_continues(group_db):
    db, group, primary, replica = group_db
    ok_adapter = MagicMock()
    fail_adapter = MagicMock()
    fail_adapter.apply_config_changes.side_effect = RuntimeError("doall failed")

    def get_adapter(node):
        return ok_adapter if node.id == primary.id else fail_adapter

    with patch(
        "app.services.node_sync.shared_domain.get_adapter_for_node",
        side_effect=get_adapter,
    ):
        result = apply_shared_domain_to_members(db, group, run_apply=True)

    assert result["success"] is False
    assert len(result["errors"]) == 1
    assert result["errors"][0]["node_id"] == replica.id
    assert result["errors"][0]["stage"] == "apply"
    # The healthy node still ran doall + recreate.
    ok_adapter.apply_config_changes.assert_called_once()
    ok_adapter.recreate_profiles.assert_called_once()
    # The failing node never reached recreate after doall raised.
    fail_adapter.recreate_profiles.assert_not_called()


def test_empty_domain_is_rejected(group_db):
    db, group, _primary, _replica = group_db
    group.shared_domain = "   "

    with patch("app.services.node_sync.shared_domain.get_adapter_for_node") as adapter_factory:
        result = apply_shared_domain_to_members(db, group, run_apply=True)

    assert result["success"] is False
    assert result["errors"] == [{"error": "shared_domain пуст"}]
    adapter_factory.assert_not_called()
