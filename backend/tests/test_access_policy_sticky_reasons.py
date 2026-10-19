"""Sticky user-level block reasons in access_policy (user_suspended / user_traffic_limit)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, OpenVpnAccessPolicy
from app.services.access_policy import AccessPolicyService


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def node(db):
    n = Node(
        name="node-1",
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=True,
        node_metadata="{}",
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture
def policy_svc(db, node, tmp_path):
    adapter = MagicMock()
    adapter.read_config_file.return_value = ""
    adapter.write_config_file.return_value = None
    adapter.ensure_openvpn_ban_check.return_value = None
    return AccessPolicyService(
        db,
        antizapret_path=tmp_path / "antizapret",
        node_id=node.id,
        node_name=node.name,
        adapter=adapter,
    )


@pytest.fixture
def ovpn_row(db, node):
    row = OpenVpnAccessPolicy(node_id=node.id, client_name="alice")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_reconcile_preserves_user_suspended(db, policy_svc, ovpn_row):
    ovpn_row.is_permanent_blocked = True
    ovpn_row.block_reason = "user_suspended"
    db.commit()
    policy_svc.reconcile_openvpn(ovpn_row.client_name)
    db.refresh(ovpn_row)
    assert ovpn_row.is_permanent_blocked is True
    assert ovpn_row.block_reason == "user_suspended"


def test_lift_reason_only_matching(db, policy_svc, ovpn_row):
    ovpn_row.is_permanent_blocked = True
    ovpn_row.block_reason = "user_suspended"
    db.commit()
    policy_svc.lift_reason_block("openvpn", ovpn_row.client_name, "user_traffic_limit", actor="t")
    db.refresh(ovpn_row)
    assert ovpn_row.block_reason == "user_suspended"
    policy_svc.lift_reason_block("openvpn", ovpn_row.client_name, "user_suspended", actor="t")
    db.refresh(ovpn_row)
    assert ovpn_row.is_permanent_blocked is False
    assert ovpn_row.block_reason in (None, "access_expired")


def test_target_reason_keeps_sticky_over_manual_permanent(db, policy_svc, ovpn_row):
    ovpn_row.is_permanent_blocked = True
    ovpn_row.block_reason = "user_traffic_limit"
    db.commit()
    policy_svc.reconcile_openvpn(ovpn_row.client_name)
    db.refresh(ovpn_row)
    assert ovpn_row.block_reason == "user_traffic_limit"
