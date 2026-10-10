"""Files copied but not applied on a replica: the group shows drift and the admin is told."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.models import SyncStatus, VpnType
from app.services.admin_notify import admin_notify_service
from app.services.node_sync import replicate, vpn_state_sync
from app.services.node_sync.replicate import (
    ReplicateOperation,
    ReplicateResult,
    _handle_client_create,
    finalize_replicate_outcome,
)
from app.services.node_sync.vpn_state_sync import Awg2NotInstalledError, ReplicaRuntimeError

WG_DRIFT = "WireGuard на реплике не применён (файлы скопированы): sync failed"


@pytest.fixture()
def sent(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(admin_notify_service, "send", lambda db, event_type, **kw: events.append((event_type, kw)))
    return events


def _group(status: SyncStatus = SyncStatus.synced) -> MagicMock:
    group = MagicMock()
    group.id = 1
    group.name = "ha"
    group.shared_domain = "vpn.example.com"
    group.primary_node_id = 1
    group.sync_status = status
    group.last_sync_error = None
    return group


def _replica() -> MagicMock:
    node = MagicMock(id=2)
    node.name = "replica"
    return node


def test_awg2_partial_apply_raises_after_import():
    primary = MagicMock()
    replica = MagicMock()
    replica.get_awg2_health.return_value = {"installed": True}
    primary.export_awg2_state_archive.return_value = b"tar"
    replica.apply_awg2_runtime.return_value = {"success": False, "errors": ["awg0: syncconf failed"]}

    with pytest.raises(ReplicaRuntimeError, match="AZ-AWG2 на реплике не применён.*awg0: syncconf failed"):
        vpn_state_sync.sync_amneziawg2_state_from_primary(primary, replica)

    replica.import_awg2_state_archive.assert_called_once_with(b"tar")


def test_sync_all_finishes_openvpn_and_awg2_then_reports_runtime_failure(monkeypatch):
    primary = MagicMock()
    primary.get_awg2_health.return_value = {"installed": True}
    monkeypatch.setattr(
        vpn_state_sync, "sync_wireguard_state_from_primary", MagicMock(side_effect=ReplicaRuntimeError(WG_DRIFT))
    )
    pki = MagicMock()
    awg2 = MagicMock()
    monkeypatch.setattr(vpn_state_sync, "sync_openvpn_pki_from_primary", pki)
    monkeypatch.setattr(vpn_state_sync, "sync_amneziawg2_state_from_primary", awg2)

    with pytest.raises(ReplicaRuntimeError, match="WireGuard на реплике не применён"):
        vpn_state_sync.sync_all_vpn_crypto_from_primary(primary, MagicMock())

    pki.assert_called_once()
    awg2.assert_called_once()


def test_sync_all_skips_awg2_when_replica_has_none(monkeypatch):
    primary = MagicMock()
    primary.get_awg2_health.return_value = {"installed": True}
    monkeypatch.setattr(vpn_state_sync, "sync_wireguard_state_from_primary", MagicMock())
    monkeypatch.setattr(vpn_state_sync, "sync_openvpn_pki_from_primary", MagicMock())
    monkeypatch.setattr(
        vpn_state_sync,
        "sync_amneziawg2_state_from_primary",
        MagicMock(side_effect=Awg2NotInstalledError("AZ-AWG2 не установлен на replica")),
    )

    vpn_state_sync.sync_all_vpn_crypto_from_primary(primary, MagicMock())


def test_sync_all_reports_awg2_copy_failure(monkeypatch):
    primary = MagicMock()
    primary.get_awg2_health.return_value = {"installed": True}
    monkeypatch.setattr(vpn_state_sync, "sync_wireguard_state_from_primary", MagicMock())
    monkeypatch.setattr(vpn_state_sync, "sync_openvpn_pki_from_primary", MagicMock())
    monkeypatch.setattr(
        vpn_state_sync,
        "sync_amneziawg2_state_from_primary",
        MagicMock(side_effect=RuntimeError("Пустой архив состояния AZ-AWG2 с primary")),
    )

    with pytest.raises(RuntimeError, match="Пустой архив"):
        vpn_state_sync.sync_all_vpn_crypto_from_primary(primary, MagicMock())


def test_client_create_records_drift_and_still_links_shadow(monkeypatch):
    primary_config = MagicMock()
    primary_config.client_name = "alice"
    primary_config.vpn_type = VpnType.wireguard
    replica = _replica()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(replicate, "_primary_adapter", lambda _db, _group: MagicMock())
    monkeypatch.setattr(replicate, "get_replica_nodes", lambda _db, _group: [replica])
    monkeypatch.setattr(replicate, "get_adapter_for_node", lambda _node: MagicMock())
    monkeypatch.setattr(
        replicate, "sync_vpn_crypto_from_primary", MagicMock(side_effect=ReplicaRuntimeError(WG_DRIFT))
    )
    monkeypatch.setattr(replicate, "upsert_shadow_config", MagicMock(return_value=MagicMock(id=99)))

    result = _handle_client_create(db, _group(), {"primary_config": primary_config})

    assert result.errors == []
    assert result.successes == [{"node_id": 2, "config_id": 99}]
    assert result.drifts == [{"node_id": 2, "node_name": "replica", "error": WG_DRIFT}]


def test_finalize_marks_drift_and_notifies_once(sent):
    db = MagicMock()
    group = _group()
    result = ReplicateResult(operation=ReplicateOperation.CLIENT_CREATE)
    result.drifts.append({"node_id": 2, "node_name": "replica", "error": WG_DRIFT})

    finalize_replicate_outcome(db, group, result)
    finalize_replicate_outcome(db, group, result)

    assert group.sync_status == SyncStatus.drift
    assert group.last_sync_error == WG_DRIFT
    assert [event for event, _ in sent] == ["node_sync_drift"]
    details = json.loads(sent[0][1]["details"])
    assert details["group_id"] == 1
    assert details["name"] == "ha"
    assert "replica" in details["summary"]
    assert details["hint"]


def test_finalize_errors_win_over_drift(sent):
    group = _group()
    result = ReplicateResult(operation=ReplicateOperation.CLIENT_CREATE)
    result.errors.append({"node_id": 3, "node_name": "other", "error": "offline"})
    result.drifts.append({"node_id": 2, "node_name": "replica", "error": WG_DRIFT})

    finalize_replicate_outcome(MagicMock(), group, result)

    assert group.sync_status == SyncStatus.failed
    assert sent == []


def test_primary_crypto_copy_marks_drift(monkeypatch, sent):
    group = _group()
    monkeypatch.setattr("app.services.node_sync.groups.get_replica_nodes", lambda _db, _group: [_replica()])
    monkeypatch.setattr("app.services.node_sync.replicate._primary_adapter", lambda _db, _group: MagicMock())
    monkeypatch.setattr("app.services.node_manager.get_adapter_for_node", lambda _node: MagicMock())
    monkeypatch.setattr(
        vpn_state_sync, "sync_vpn_crypto_from_primary", MagicMock(side_effect=ReplicaRuntimeError(WG_DRIFT))
    )

    result = vpn_state_sync.replicate_primary_crypto_to_replicas(
        MagicMock(), group, MagicMock(client_name="alice", vpn_type=VpnType.wireguard)
    )

    assert result["errors"] == []
    assert [entry["node_id"] for entry in result["drifts"]] == [2]
    assert [entry["node_id"] for entry in result["successes"]] == [2]
    assert group.sync_status == SyncStatus.drift
    assert [event for event, _ in sent] == ["node_sync_drift"]
