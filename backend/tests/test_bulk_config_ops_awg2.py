"""Bulk operations treat AmneziaWG 2.0 clients as AWG2, never as WireGuard clients with the same name."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.services import bulk_config_ops


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


def _node(db) -> Node:
    node = Node(
        name="primary",
        host="127.0.0.1",
        port=9100,
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


def _config(db, node: Node, name: str, vpn_type: VpnType) -> VpnConfig:
    owner = User(username=f"owner-{name}", password_hash="x", role=UserRole.admin)
    db.add(owner)
    db.commit()
    config = VpnConfig(node_id=node.id, client_name=name, vpn_type=vpn_type, owner_id=owner.id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _run(session_factory, tmp_path, node, config, operation, adapter, svc):
    with (
        patch.object(bulk_config_ops, "SessionLocal", session_factory),
        patch.object(bulk_config_ops, "get_active_adapter", return_value=adapter),
        patch.object(bulk_config_ops, "get_node_antizapret_path", return_value=tmp_path),
        patch.object(bulk_config_ops, "AccessPolicyService", return_value=svc),
        patch.object(bulk_config_ops, "maybe_replicate_policy_op") as replicate_policy,
        patch.object(bulk_config_ops, "get_active_node", return_value=SimpleNamespace(id=node.id, name=node.name)),
        patch.object(bulk_config_ops, "find_sync_group_for_primary", return_value=None),
        patch.object(bulk_config_ops.admin_notify_service, "send_config_delete"),
    ):
        result = bulk_config_ops._run_single_op(
            operation=operation,
            config_id=config.id,
            node_id=node.id,
            block_days=3,
            renew_cert_days=3650,
            owner_id=None,
            actor_username="admin",
        )
    return result, replicate_policy


@pytest.mark.parametrize(
    ("operation", "awg2_method", "wg_method", "args"),
    [
        ("block_temp", "awg2_temp_block", "wg_temp_block", ("ivan", 3)),
        ("block_perm", "awg2_permanent_block", "wg_permanent_block", ("ivan",)),
        ("unblock", "awg2_unblock", "wg_unblock", ("ivan",)),
    ],
)
def test_awg2_policy_ops_use_awg2_methods(db, session_factory, tmp_path, operation, awg2_method, wg_method, args):
    node = _node(db)
    config = _config(db, node, "ivan", VpnType.amneziawg2)
    svc = MagicMock()

    result, replicate_policy = _run(session_factory, tmp_path, node, config, operation, MagicMock(), svc)

    assert result["ok"] is True
    getattr(svc, awg2_method).assert_called_once_with(*args, actor="admin")
    getattr(svc, wg_method).assert_not_called()
    assert replicate_policy.call_args.kwargs["vpn_type"] == VpnType.amneziawg2


def test_wireguard_policy_ops_still_use_wg_methods(db, session_factory, tmp_path):
    node = _node(db)
    config = _config(db, node, "ivan", VpnType.wireguard)
    svc = MagicMock()

    result, _ = _run(session_factory, tmp_path, node, config, "block_temp", MagicMock(), svc)

    assert result["ok"] is True
    svc.wg_temp_block.assert_called_once_with("ivan", 3, actor="admin")
    svc.awg2_temp_block.assert_not_called()


def test_awg2_bulk_delete_deletes_awg2_client(db, session_factory, tmp_path):
    node = _node(db)
    config = _config(db, node, "ivan", VpnType.amneziawg2)
    adapter = MagicMock()

    result, _ = _run(session_factory, tmp_path, node, config, "delete", adapter, MagicMock())

    assert result["ok"] is True
    adapter.awg2_delete_client.assert_called_once_with("ivan")
    adapter.delete_wireguard_client.assert_not_called()
    db.expire_all()
    assert db.query(VpnConfig).count() == 0
