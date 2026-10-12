"""Verify compares what the replica actually runs: live WireGuard peers and AWG2 clients."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models import SyncStatus
from app.schemas import WireGuardPeer
from app.services.node_sync.verify import verify_sync_group
from app.services.openvpn_pki import ProfileValidationResult


def _group(status: SyncStatus = SyncStatus.synced) -> MagicMock:
    group = MagicMock()
    group.id = 1
    group.primary_node_id = 1
    group.replica_node_ids = "[2]"
    group.shared_domain = "vpn.example.com"
    group.last_verify_result = None
    group.sync_status = status
    group.last_sync_error = None
    return group


def _adapter(*, peers=(), awg2_installed=False, awg2_clients=()) -> MagicMock:
    adapter = MagicMock()
    adapter.list_openvpn_clients.return_value = []
    adapter.list_wireguard_clients.return_value = ["alice"]
    adapter.get_antizapret_fingerprints.return_value = {}
    adapter.get_config_file_fingerprints.return_value = {}
    adapter.parse_wireguard_status.return_value = list(peers)
    adapter.get_awg2_health.return_value = {"installed": awg2_installed}
    adapter.list_amneziawg2_clients.return_value = list(awg2_clients)
    return adapter


def _peer(interface: str, key: str, name: str | None = None) -> WireGuardPeer:
    return WireGuardPeer(interface=interface, public_key=key, client_name=name)


def _verify(primary, replica, *, group=None):
    group = group or _group()
    primary_node = MagicMock(id=1)
    primary_node.name = "primary"
    replica_node = MagicMock(id=2)
    replica_node.name = "replica"
    db = MagicMock()
    db.get.side_effect = lambda _model, node_id: primary_node if node_id == 1 else replica_node
    with patch("app.services.node_sync.verify._refresh_node_online", return_value=True), patch(
        "app.services.node_sync.verify.get_adapter_for_node",
        side_effect=lambda node: primary if node.id == 1 else replica,
    ), patch(
        "app.services.node_sync.verify.validate_all_openvpn_profiles",
        return_value=ProfileValidationResult(ready=True, issues=()),
    ):
        return verify_sync_group(db, group)


def _mismatches(result) -> list[dict]:
    return result["replicas"][0]["mismatches"]


def test_peer_missing_from_replica_runtime_is_a_mismatch():
    primary = _adapter(peers=[_peer("vpn", "KEY-A", "alice")])
    replica = _adapter(peers=[])

    result = _verify(primary, replica)

    assert result["ready"] is False
    assert _mismatches(result) == [{"kind": "wireguard_peers", "only_primary": ["vpn: alice"], "only_replica": []}]


def test_peers_on_other_interfaces_are_ignored():
    primary = _adapter(peers=[_peer("vpn", "KEY-A", "alice"), _peer("warp", "CF-1")])
    replica = _adapter(peers=[_peer("vpn", "KEY-A", "alice"), _peer("warp", "CF-2")])

    result = _verify(primary, replica)

    assert result["ready"] is True


def test_awg2_client_missing_on_replica_is_a_mismatch():
    primary = _adapter(awg2_installed=True, awg2_clients=["bob"])
    replica = _adapter(awg2_installed=True, awg2_clients=[])

    result = _verify(primary, replica)

    assert _mismatches(result) == [{"kind": "awg2_clients", "only_primary": ["bob"], "only_replica": []}]


def test_awg2_not_compared_when_primary_has_no_awg2():
    primary = _adapter(awg2_installed=False)
    replica = _adapter(awg2_installed=False, awg2_clients=["stale"])

    result = _verify(primary, replica)

    assert result["ready"] is True
    replica.list_amneziawg2_clients.assert_not_called()


def test_ready_check_clears_drift_status():
    group = _group(SyncStatus.drift)
    group.last_sync_error = "WireGuard на реплике не применён (файлы скопированы): x"

    result = _verify(_adapter(), _adapter(), group=group)

    assert result["ready"] is True
    assert group.sync_status == SyncStatus.synced
    assert group.last_sync_error is None
