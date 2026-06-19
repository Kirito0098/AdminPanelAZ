"""HA auto-sync AntiZapret setup settings replication tests (step C.1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus, UserActionLog
from app.services.node_sync.antizapret_sync import replicate_antizapret_settings
from app.services.node_sync.groups import serialize_replica_node_ids


@pytest.fixture()
def auto_group_db(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online)
    replica = Node(name="replica", host="10.0.0.2", port=9100, status=NodeStatus.online)
    db_session.add_all([primary, replica])
    db_session.commit()
    group = NodeSyncGroup(
        name="HA",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    db_session.add(group)
    db_session.commit()
    return db_session, group, primary, replica


def test_replicate_route_all_calls_adapter_per_replica(auto_group_db):
    db, group, _primary, replica = auto_group_db
    replica_adapter = MagicMock()
    replica_adapter.update_antizapret_settings.return_value = {"route_all": "y", "needs_apply": True}

    with patch("app.services.node_sync.antizapret_sync.get_adapter_for_node", return_value=replica_adapter):
        result = replicate_antizapret_settings(db, group, {"route_all": True})

    assert result.skipped is False
    assert result.errors == []
    assert len(result.successes) == 1
    assert result.successes[0]["node_id"] == replica.id
    assert group.sync_status == SyncStatus.synced
    replica_adapter.update_antizapret_settings.assert_called_once_with({"route_all": True})


def test_replicate_skips_excluded_warp_keys_but_keeps_hosts(auto_group_db):
    db, group, _primary, replica = auto_group_db
    replica_adapter = MagicMock()
    replica_adapter.update_antizapret_settings.return_value = {"needs_apply": False}

    updates = {
        "ANTIZAPRET_WARP": "y",
        "VPN_WARP": "n",
        "route_all": "y",
        "openvpn_host": "vpn.example.com",
        "wireguard_host": "vpn.example.com",
    }

    with patch("app.services.node_sync.antizapret_sync.get_adapter_for_node", return_value=replica_adapter):
        result = replicate_antizapret_settings(db, group, updates)

    assert result.errors == []
    replica_adapter.update_antizapret_settings.assert_called_once_with(
        {
            "route_all": "y",
            "openvpn_host": "vpn.example.com",
            "wireguard_host": "vpn.example.com",
        }
    )
    assert group.sync_status == SyncStatus.synced


def test_replicate_partial_failure_sets_failed_and_audits(auto_group_db, monkeypatch):
    db, group, _primary, replica = auto_group_db
    replica2 = Node(name="replica2", host="10.0.0.3", port=9100, status=NodeStatus.online)
    db.add(replica2)
    db.commit()
    group.replica_node_ids = serialize_replica_node_ids([replica.id, replica2.id])
    db.commit()

    adapter_ok = MagicMock()
    adapter_fail = MagicMock()
    adapter_fail.update_antizapret_settings.side_effect = RuntimeError("adapter down")

    def get_adapter(node):
        if node.id == replica.id:
            return adapter_ok
        return adapter_fail

    monkeypatch.setattr(
        "app.services.node_sync.replicate.get_settings",
        lambda: Settings(audit_log_enabled=True),
    )

    with patch("app.services.node_sync.antizapret_sync.get_adapter_for_node", side_effect=get_adapter):
        result = replicate_antizapret_settings(db, group, {"route_all": "y"})

    assert len(result.successes) == 1
    assert len(result.errors) == 1
    assert result.errors[0]["node_id"] == replica2.id
    assert group.sync_status == SyncStatus.failed
    assert group.last_sync_error == "adapter down"
    log = (
        db.query(UserActionLog)
        .filter(UserActionLog.action == "ha_replicate_partial_failure")
        .one()
    )
    assert "settings_keys=route_all" in log.details
    assert "successful_replicas=replica" in log.details
    assert "failed_replicas=replica2" in log.details


def test_manual_mode_skips_replicate(auto_group_db):
    db, group, _primary, replica = auto_group_db
    group.sync_mode = "manual_full"
    db.commit()

    replica_adapter = MagicMock()

    with patch("app.services.node_sync.antizapret_sync.get_adapter_for_node", return_value=replica_adapter):
        result = replicate_antizapret_settings(db, group, {"route_all": "y"})

    assert result.skipped is True
    assert result.successes == []
    assert result.errors == []
    replica_adapter.update_antizapret_settings.assert_not_called()
