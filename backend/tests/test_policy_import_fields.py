"""HA policy field copy must match real model columns."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    AmneziaWg2AccessPolicy,
    Node,
    NodeStatus,
    OpenVpnAccessPolicy,
    VpnType,
    WgAccessPolicy,
)
from app.services.policy_import import (
    _AWG2_POLICY_FIELDS,
    _OVPN_POLICY_FIELDS,
    _WG_POLICY_FIELDS,
    copy_single_client_policy,
)


def test_policy_field_lists_match_model_attributes():
    assert not [f for f in _OVPN_POLICY_FIELDS if not hasattr(OpenVpnAccessPolicy, f)]
    assert not [f for f in _WG_POLICY_FIELDS if not hasattr(WgAccessPolicy, f)]
    assert not [f for f in _AWG2_POLICY_FIELDS if not hasattr(AmneziaWg2AccessPolicy, f)]
    assert "access_until" not in _WG_POLICY_FIELDS
    assert "expires_at" in _WG_POLICY_FIELDS
    assert "traffic_limit_bytes" in _AWG2_POLICY_FIELDS
    assert "traffic_limit_period_days" in _AWG2_POLICY_FIELDS


def test_copy_single_client_wg_policy_copies_expires_at_and_traffic():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        primary = Node(
            name="primary",
            host="10.0.0.1",
            port=9100,
            api_key_hash="",
            api_key_encrypted="",
            status=NodeStatus.online,
            is_local=True,
            node_metadata="{}",
        )
        replica = Node(
            name="replica",
            host="10.0.0.2",
            port=9100,
            api_key_hash="",
            api_key_encrypted="",
            status=NodeStatus.online,
            is_local=False,
            node_metadata="{}",
        )
        db.add_all([primary, replica])
        db.flush()
        until = datetime(2030, 2, 1, tzinfo=timezone.utc).replace(tzinfo=None)
        db.add(
            WgAccessPolicy(
                node_id=primary.id,
                client_name="alice",
                expires_at=until,
                is_temp_blocked=False,
                is_permanent_blocked=False,
                traffic_limit_bytes=1024,
                traffic_limit_period_days=7,
                updated_by="admin",
            )
        )
        db.commit()

        copied = copy_single_client_policy(
            db, primary, replica, "alice", vpn_type=VpnType.wireguard
        )
        assert copied == 1
        row = (
            db.query(WgAccessPolicy)
            .filter_by(node_id=replica.id, client_name="alice")
            .one()
        )
        assert row.expires_at == until
        assert row.traffic_limit_bytes == 1024
        assert row.traffic_limit_period_days == 7
    finally:
        db.close()
        engine.dispose()
