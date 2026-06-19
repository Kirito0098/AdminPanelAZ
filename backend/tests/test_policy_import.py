"""Unit tests for policy_import service."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models import Node, NodeStatus, OpenVpnAccessPolicy, WgAccessPolicy
from app.services.access_policy import NODE_DEFAULT_POLICY_CLIENT
from app.services.policy_import import copy_access_policies_from_node


@pytest.fixture()
def policy_nodes(db_session):
    primary = Node(name="primary", host="10.0.0.1", port=9100, status=NodeStatus.online)
    replica = Node(name="replica", host="10.0.0.2", port=9100, status=NodeStatus.online)
    db_session.add_all([primary, replica])
    db_session.commit()
    return db_session, primary, replica


def test_copy_access_policies_creates_rows_on_replica(policy_nodes):
    db, primary, replica = policy_nodes
    expires = datetime(2030, 1, 1, 12, 0, 0)
    db.add_all(
        [
            OpenVpnAccessPolicy(
                node_id=primary.id,
                client_name="alice",
                is_permanent_blocked=True,
                block_reason="manual",
                traffic_limit_bytes=1_000_000,
            ),
            WgAccessPolicy(
                node_id=primary.id,
                client_name="bob",
                is_temp_blocked=True,
                expires_at=expires,
            ),
            OpenVpnAccessPolicy(
                node_id=primary.id,
                client_name=NODE_DEFAULT_POLICY_CLIENT,
                traffic_limit_bytes=5_000_000,
            ),
        ]
    )
    db.commit()

    copied = copy_access_policies_from_node(db, primary, replica)
    assert copied == 3

    ovpn = (
        db.query(OpenVpnAccessPolicy)
        .filter(
            OpenVpnAccessPolicy.node_id == replica.id,
            OpenVpnAccessPolicy.client_name == "alice",
        )
        .first()
    )
    assert ovpn is not None
    assert ovpn.is_permanent_blocked is True
    assert ovpn.traffic_limit_bytes == 1_000_000

    wg = (
        db.query(WgAccessPolicy)
        .filter(WgAccessPolicy.node_id == replica.id, WgAccessPolicy.client_name == "bob")
        .first()
    )
    assert wg is not None
    assert wg.is_temp_blocked is True
    assert wg.expires_at == expires


def test_copy_access_policies_idempotent(policy_nodes):
    db, primary, replica = policy_nodes
    db.add(
        OpenVpnAccessPolicy(
            node_id=primary.id,
            client_name="alice",
            is_permanent_blocked=True,
        )
    )
    db.commit()

    first = copy_access_policies_from_node(db, primary, replica)
    primary_row = (
        db.query(OpenVpnAccessPolicy)
        .filter(
            OpenVpnAccessPolicy.node_id == primary.id,
            OpenVpnAccessPolicy.client_name == "alice",
        )
        .first()
    )
    primary_row.is_permanent_blocked = False
    db.commit()

    second = copy_access_policies_from_node(db, primary, replica)
    assert first == 1
    assert second == 0

    replica_row = (
        db.query(OpenVpnAccessPolicy)
        .filter(
            OpenVpnAccessPolicy.node_id == replica.id,
            OpenVpnAccessPolicy.client_name == "alice",
        )
        .first()
    )
    assert replica_row is not None
    assert replica_row.is_permanent_blocked is False
