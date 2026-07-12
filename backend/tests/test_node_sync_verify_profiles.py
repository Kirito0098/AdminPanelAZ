"""Verify includes OpenVPN profile certificate validation."""

from unittest.mock import MagicMock, patch

from app.services.node_sync.verify import verify_sync_group
from app.services.openvpn_pki import ProfileCertIssue, ProfileValidationResult


def test_verify_marks_not_ready_when_profile_has_revoked_cert():
    group = MagicMock()
    group.primary_node_id = 1
    group.replica_node_ids = "[2]"
    group.shared_domain = "vpn.example.com"
    group.last_verify_result = None
    group.last_verify_at = None

    primary_node = MagicMock()
    primary_node.id = 1
    primary_node.name = "primary"
    primary_node.status = "online"

    replica_node = MagicMock()
    replica_node.id = 2
    replica_node.name = "replica"
    replica_node.status = "online"

    db = MagicMock()
    db.get.side_effect = lambda model, node_id: primary_node if node_id == 1 else replica_node

    primary_adapter = MagicMock()
    primary_adapter.list_openvpn_clients.return_value = ["client-a"]
    primary_adapter.list_wireguard_clients.return_value = []
    primary_adapter.get_antizapret_fingerprints.return_value = {}
    primary_adapter.get_config_file_fingerprints.return_value = {}

    replica_adapter = MagicMock()
    replica_adapter.list_openvpn_clients.return_value = ["client-a"]
    replica_adapter.list_wireguard_clients.return_value = []
    replica_adapter.get_antizapret_fingerprints.return_value = {}
    replica_adapter.get_config_file_fingerprints.return_value = {}

    bad_validation = ProfileValidationResult(
        ready=False,
        issues=(
            ProfileCertIssue(
                client_name="client-a",
                path="/root/antizapret/client/openvpn/vpn/vpn-client-a.ovpn",
                filename="vpn-client-a.ovpn",
                serial_hex="ABCDEF",
                status="revoked",
            ),
        ),
    )

    with patch("app.services.node_sync.verify._refresh_node_online", return_value=True), patch(
        "app.services.node_sync.verify.get_adapter_for_node",
        side_effect=lambda node: primary_adapter if node.id == 1 else replica_adapter,
    ), patch(
        "app.services.node_sync.verify.validate_all_openvpn_profiles",
        side_effect=lambda adapter: bad_validation if adapter is primary_adapter else ProfileValidationResult(ready=True, issues=()),
    ):
        result = verify_sync_group(db, group)

    assert result["ready"] is False
    assert result["openvpn_profile_certs"]["ready"] is False
    assert result["openvpn_profile_certs"]["primary_issues"][0]["client_name"] == "client-a"
    replica_entry = result["replicas"][0]
    assert replica_entry["online"] is True
