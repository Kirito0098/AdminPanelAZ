"""Deleting a client also deletes its access policy (block, traffic limit, access deadline)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    AmneziaWg2AccessPolicy,
    Node,
    NodeStatus,
    OpenVpnAccessPolicy,
    User,
    UserRole,
    VpnConfig,
    VpnType,
    WgAccessPolicy,
)
from app.routers import configs as configs_router
from app.services import bulk_config_ops
from app.services.access_policy import delete_client_access_policies
from app.services.node_sync import replicate


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def _node(db, *, name: str = "primary", port: int = 9100) -> Node:
    node = Node(
        name=name,
        host="127.0.0.1",
        port=port,
        api_key_hash="hash",
        api_key_encrypted="enc",
        status=NodeStatus.online,
        is_local=True,
        node_kind="vpn",
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _owner(db) -> User:
    user = User(username="admin", password_hash="x", role=UserRole.admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _config(db, node: Node, owner: User, name: str, vpn_type: VpnType, **extra) -> VpnConfig:
    config = VpnConfig(node_id=node.id, client_name=name, vpn_type=vpn_type, owner_id=owner.id, **extra)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def test_openvpn_policy_is_deleted_with_the_client(db):
    node, owner = _node(db), _owner(db)
    config = _config(db, node, owner, "mira", VpnType.openvpn)
    db.add(OpenVpnAccessPolicy(node_id=node.id, client_name="mira", is_permanent_blocked=True))
    db.add(OpenVpnAccessPolicy(node_id=node.id, client_name="other", is_permanent_blocked=True))
    db.commit()

    assert delete_client_access_policies(db, config) == 1
    db.commit()

    assert [row.client_name for row in db.query(OpenVpnAccessPolicy).all()] == ["other"]


def test_wireguard_policy_is_kept_while_a_case_twin_remains(db):
    node, owner = _node(db), _owner(db)
    upper = _config(db, node, owner, "Ivan", VpnType.wireguard)
    lower = _config(db, node, owner, "ivan", VpnType.wireguard)
    db.add(WgAccessPolicy(node_id=node.id, client_name="ivan", is_permanent_blocked=True))
    db.commit()

    assert delete_client_access_policies(db, upper) == 0
    db.delete(upper)
    db.commit()
    assert delete_client_access_policies(db, lower) == 1
    db.commit()

    assert db.query(WgAccessPolicy).count() == 0


def test_awg2_policy_on_another_node_is_untouched(db):
    owner = _owner(db)
    node_a = _node(db, name="a", port=9100)
    node_b = _node(db, name="b", port=9101)
    config = _config(db, node_a, owner, "Olga", VpnType.amneziawg2)
    db.add(AmneziaWg2AccessPolicy(node_id=node_a.id, client_name="olga", is_temp_blocked=True))
    db.add(AmneziaWg2AccessPolicy(node_id=node_b.id, client_name="olga", is_temp_blocked=True))
    db.commit()

    assert delete_client_access_policies(db, config) == 1
    db.commit()

    assert [row.node_id for row in db.query(AmneziaWg2AccessPolicy).all()] == [node_b.id]


def test_delete_route_drops_the_policy(db):
    node, owner = _node(db), _owner(db)
    config = _config(db, node, owner, "olga", VpnType.amneziawg2)
    db.add(AmneziaWg2AccessPolicy(node_id=node.id, client_name="olga", is_temp_blocked=True))
    db.commit()
    user = SimpleNamespace(id=owner.id, username="admin", role=UserRole.admin)

    with (
        patch.object(configs_router, "_get_config_for_active_node", return_value=config),
        patch.object(configs_router, "_can_mutate_config", return_value=True),
        patch.object(configs_router, "require_ha_primary_for_client_ops"),
        patch.object(configs_router, "get_active_adapter", return_value=MagicMock()),
        patch.object(configs_router, "get_active_node", return_value=node),
        patch.object(configs_router, "find_sync_group_for_primary", return_value=None),
        patch.object(configs_router.admin_notify_service, "send_config_delete"),
        patch.object(configs_router, "get_client_timezone_from_request", return_value="UTC"),
    ):
        configs_router.delete_config(config.id, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")), db, user)

    assert db.query(VpnConfig).count() == 0
    assert db.query(AmneziaWg2AccessPolicy).count() == 0


def test_bulk_delete_drops_the_policy(db, session_factory, tmp_path):
    node, owner = _node(db), _owner(db)
    config = _config(db, node, owner, "bob", VpnType.wireguard)
    db.add(WgAccessPolicy(node_id=node.id, client_name="bob", is_permanent_blocked=True))
    db.commit()

    with (
        patch.object(bulk_config_ops, "SessionLocal", session_factory),
        patch.object(bulk_config_ops, "get_active_adapter", return_value=MagicMock()),
        patch.object(bulk_config_ops, "get_node_antizapret_path", return_value=tmp_path),
        patch.object(bulk_config_ops, "get_active_node", return_value=SimpleNamespace(id=node.id, name=node.name)),
        patch.object(bulk_config_ops, "find_sync_group_for_primary", return_value=None),
        patch.object(bulk_config_ops.admin_notify_service, "send_config_delete"),
    ):
        result = bulk_config_ops._run_single_op(
            operation="delete",
            config_id=config.id,
            node_id=node.id,
            block_days=7,
            renew_cert_days=3650,
            owner_id=None,
            actor_username="admin",
        )

    assert result["ok"] is True
    db.expire_all()
    assert db.query(WgAccessPolicy).count() == 0


def test_replica_delete_drops_the_shadow_policy(db):
    owner = _owner(db)
    primary = _node(db, name="primary", port=9100)
    replica_node = _node(db, name="replica", port=9101)
    primary_config = _config(db, primary, owner, "olga", VpnType.amneziawg2)
    shadow = _config(
        db, replica_node, owner, "olga", VpnType.amneziawg2, ha_primary_config_id=primary_config.id
    )
    db.add(AmneziaWg2AccessPolicy(node_id=replica_node.id, client_name="olga", is_temp_blocked=True))
    db.commit()

    with (
        patch.object(replicate, "_primary_adapter", return_value=MagicMock()),
        patch.object(replicate, "get_shadow_configs", return_value=[shadow]),
        patch.object(replicate, "get_adapter_for_node", return_value=MagicMock()),
        patch.object(replicate, "sync_vpn_crypto_from_primary"),
    ):
        result = replicate._handle_client_delete(db, SimpleNamespace(id=7), {"primary_config": primary_config})
    db.commit()

    assert result.errors == []
    assert db.query(VpnConfig).filter_by(node_id=replica_node.id).count() == 0
    assert db.query(AmneziaWg2AccessPolicy).count() == 0
