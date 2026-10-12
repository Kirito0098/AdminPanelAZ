"""Deleting an OpenVPN client removes its name from the node's banned_clients file."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.routers import configs as configs_router
from app.services import bulk_config_ops
from app.services.access_policy import (
    clear_cooldown_ban,
    forget_deleted_openvpn_client,
    is_cooldown_ban_active,
    register_cooldown_ban,
)
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


def _config(db, node: Node, owner: User, name: str, **extra) -> VpnConfig:
    config = VpnConfig(node_id=node.id, client_name=name, vpn_type=VpnType.openvpn, owner_id=owner.id, **extra)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _ban_adapter(content: str) -> MagicMock:
    adapter = MagicMock()
    adapter.read_config_file.return_value = content
    return adapter


def test_forget_removes_only_the_deleted_name():
    adapter = _ban_adapter("# banned\nmira\nother\n")

    forget_deleted_openvpn_client(MagicMock(), adapter, node_id=1, client_name="mira")

    adapter.read_config_file.assert_called_once_with("banned_clients")
    adapter.write_config_file.assert_called_once_with("banned_clients", "other\n")
    adapter.ensure_openvpn_ban_check.assert_called_once_with()


def test_forget_skips_the_write_when_the_name_is_not_banned():
    adapter = _ban_adapter("other\n")

    forget_deleted_openvpn_client(MagicMock(), adapter, node_id=1, client_name="mira")

    adapter.write_config_file.assert_not_called()


def test_forget_clears_the_disconnect_cooldown_ban():
    register_cooldown_ban(1, "mira", 60)
    try:
        forget_deleted_openvpn_client(MagicMock(), _ban_adapter(""), node_id=1, client_name="mira")

        assert is_cooldown_ban_active(1, "mira") is False
    finally:
        clear_cooldown_ban(1, "mira")


def test_forget_does_not_raise_when_the_node_fails():
    adapter = MagicMock()
    adapter.read_config_file.side_effect = ConnectionError("node down")

    forget_deleted_openvpn_client(MagicMock(), adapter, node_id=1, client_name="mira")

    adapter.write_config_file.assert_not_called()


def test_delete_route_unbans_the_openvpn_name(db):
    node, owner = _node(db), _owner(db)
    config = _config(db, node, owner, "mira")
    adapter = _ban_adapter("mira\nother\n")
    user = SimpleNamespace(id=owner.id, username="admin", role=UserRole.admin)

    with (
        patch.object(configs_router, "_get_config_for_active_node", return_value=config),
        patch.object(configs_router, "_can_mutate_config", return_value=True),
        patch.object(configs_router, "require_ha_primary_for_client_ops"),
        patch.object(configs_router, "get_active_adapter", return_value=adapter),
        patch.object(configs_router, "get_active_node", return_value=node),
        patch.object(configs_router, "find_sync_group_for_primary", return_value=None),
        patch.object(configs_router.admin_notify_service, "send_config_delete"),
        patch.object(configs_router, "get_client_timezone_from_request", return_value="UTC"),
    ):
        configs_router.delete_config(config.id, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")), db, user)

    adapter.delete_openvpn_client.assert_called_once_with("mira")
    adapter.write_config_file.assert_called_once_with("banned_clients", "other\n")
    assert db.query(VpnConfig).count() == 0


def test_bulk_delete_unbans_the_openvpn_name(db, session_factory, tmp_path):
    node, owner = _node(db), _owner(db)
    config = _config(db, node, owner, "mira")
    adapter = _ban_adapter("mira\n")

    with (
        patch.object(bulk_config_ops, "SessionLocal", session_factory),
        patch.object(bulk_config_ops, "get_active_adapter", return_value=adapter),
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
    adapter.delete_openvpn_client.assert_called_once_with("mira")
    adapter.write_config_file.assert_called_once_with("banned_clients", "")


def test_replica_delete_unbans_the_name_on_the_replica(db):
    owner = _owner(db)
    primary = _node(db, name="primary", port=9100)
    replica_node = _node(db, name="replica", port=9101)
    primary_config = _config(db, primary, owner, "mira")
    shadow = _config(db, replica_node, owner, "mira", ha_primary_config_id=primary_config.id)
    primary_adapter = _ban_adapter("mira\n")
    replica_adapter = _ban_adapter("mira\nother\n")

    with (
        patch.object(replicate, "_primary_adapter", return_value=primary_adapter),
        patch.object(replicate, "get_shadow_configs", return_value=[shadow]),
        patch.object(replicate, "get_adapter_for_node", return_value=replica_adapter),
        patch.object(replicate, "sync_vpn_crypto_from_primary"),
    ):
        result = replicate._handle_client_delete(db, SimpleNamespace(id=7), {"primary_config": primary_config})
    db.commit()

    assert result.errors == []
    replica_adapter.write_config_file.assert_called_once_with("banned_clients", "other\n")
    primary_adapter.write_config_file.assert_not_called()
    assert db.query(VpnConfig).filter_by(node_id=replica_node.id).count() == 0
