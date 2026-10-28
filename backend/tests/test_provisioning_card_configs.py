"""The user card must show every config the user owns, not only plan-namespace names."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.routers import users as users_router


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    try:
        yield make
    finally:
        engine.dispose()


def test_card_shows_a_config_reassigned_outside_the_plan_namespace(factory):
    with factory() as db:
        owner = User(username="test10", password_hash="x", role=UserRole.user, client_base_name="test10")
        db.add(owner)
        db.add_all(
            [
                Node(id=1, name="1Cent-EE", host="h1", is_local=True, status=NodeStatus.online),
                Node(id=2, name="2Cent-EE", host="h2", is_local=False, status=NodeStatus.online),
            ]
        )
        db.commit()
        db.add_all(
            [
                VpnConfig(node_id=1, client_name="test10", vpn_type=VpnType.wireguard, owner_id=owner.id),
                VpnConfig(node_id=2, client_name="android_test", vpn_type=VpnType.openvpn, owner_id=owner.id),
            ]
        )
        db.commit()

        groups = users_router._group_provision_configs(db, owner)

    assert {group.name for group in groups} == {"test10", "android_test"}
    reassigned = next(group for group in groups if group.name == "android_test")
    assert [(node.node_label, node.vpn_type) for node in reassigned.nodes] == [("2Cent-EE", "openvpn")]


def test_card_hides_ha_shadow_configs(factory):
    with factory() as db:
        owner = User(username="ha_user", password_hash="x", role=UserRole.user, client_base_name="ha_user")
        db.add(owner)
        db.add_all(
            [
                Node(id=1, name="primary", host="h1", is_local=True, status=NodeStatus.online),
                Node(id=2, name="replica", host="h2", is_local=False, status=NodeStatus.online),
            ]
        )
        db.commit()
        primary = VpnConfig(
            node_id=1, client_name="ha_user", vpn_type=VpnType.wireguard, owner_id=owner.id
        )
        db.add(primary)
        db.commit()
        db.refresh(primary)
        db.add(
            VpnConfig(
                node_id=2,
                client_name="ha_user",
                vpn_type=VpnType.wireguard,
                owner_id=owner.id,
                ha_primary_config_id=primary.id,
            )
        )
        db.commit()

        groups = users_router._group_provision_configs(db, owner)

    assert len(groups) == 1
    assert len(groups[0].nodes) == 1
    assert groups[0].nodes[0].node_label == "primary"
