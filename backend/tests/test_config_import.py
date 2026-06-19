"""Unit tests for config_import service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.services.config_import import import_clients_from_disk


@pytest.fixture()
def import_db(db_session):
    node = Node(name="node-1", host="10.0.0.1", port=9100, status=NodeStatus.online)
    admin = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
    db_session.add_all([node, admin])
    db_session.commit()
    return db_session, node, admin


def test_import_clients_from_disk_creates_openvpn_and_wireguard(import_db):
    db, node, admin = import_db
    adapter = MagicMock()
    adapter.list_openvpn_clients.return_value = ["ovpn-client"]
    adapter.list_wireguard_clients.return_value = ["wg-client"]

    with patch("app.services.config_import.get_adapter_for_node", return_value=adapter):
        with patch(
            "app.services.config_import.resolve_openvpn_cert_days_remaining",
            return_value=30,
        ):
            imported = import_clients_from_disk(db, node, admin.id)

    assert imported == 2
    configs = db.query(VpnConfig).filter(VpnConfig.node_id == node.id).all()
    assert len(configs) == 2
    by_name = {(c.client_name, c.vpn_type): c for c in configs}
    assert by_name[("ovpn-client", VpnType.openvpn)].owner_id == admin.id
    assert by_name[("ovpn-client", VpnType.openvpn)].cert_expire_days == 30
    assert by_name[("wg-client", VpnType.wireguard)].owner_id == admin.id


def test_import_clients_from_disk_idempotent(import_db):
    db, node, admin = import_db
    adapter = MagicMock()
    adapter.list_openvpn_clients.return_value = ["alice"]
    adapter.list_wireguard_clients.return_value = ["bob"]

    with patch("app.services.config_import.get_adapter_for_node", return_value=adapter):
        with patch(
            "app.services.config_import.resolve_openvpn_cert_days_remaining",
            return_value=None,
        ):
            first = import_clients_from_disk(db, node, admin.id)
            second = import_clients_from_disk(db, node, admin.id)

    assert first == 2
    assert second == 0
    assert db.query(VpnConfig).filter(VpnConfig.node_id == node.id).count() == 2


def test_import_clients_from_disk_updates_openvpn_cert_days(import_db):
    db, node, admin = import_db
    existing = VpnConfig(
        node_id=node.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=admin.id,
        cert_expire_days=None,
    )
    db.add(existing)
    db.commit()

    adapter = MagicMock()
    adapter.list_openvpn_clients.return_value = ["alice"]
    adapter.list_wireguard_clients.return_value = []

    with patch("app.services.config_import.get_adapter_for_node", return_value=adapter):
        with patch(
            "app.services.config_import.resolve_openvpn_cert_days_remaining",
            return_value=14,
        ):
            imported = import_clients_from_disk(db, node, admin.id)

    assert imported == 0
    db.refresh(existing)
    assert existing.cert_expire_days == 14
