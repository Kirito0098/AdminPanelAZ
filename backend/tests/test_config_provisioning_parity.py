"""Stage 1 Task 3: provision_config must use the adapter of the node it is given."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnType
from app.services.admin_notify import admin_notify_service
from app.services.config_provisioning import provision_config


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _node(db, *, name: str, port: int) -> Node:
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


def _user(db, *, username: str, role: UserRole) -> User:
    user = User(username=username, password_hash="x", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_provision_config_uses_given_node_adapter(db, monkeypatch):
    _node(db, name="primary", port=9100)
    other = _node(db, name="other", port=9101)
    owner = _user(db, username="ivan", role=UserRole.user)
    actor = _user(db, username="admin", role=UserRole.admin)

    adapter = MagicMock()

    def fake_get_adapter_for_node(node):
        return adapter if node.id == other.id else MagicMock()

    monkeypatch.setattr("app.services.config_provisioning.get_adapter_for_node", fake_get_adapter_for_node)

    patches = {
        "recreate_openvpn_profiles_after_admin_change": MagicMock(),
        "load_node_remote_hosts": MagicMock(return_value=[]),
        "refresh_config_cert_expiry": MagicMock(),
        "purge_traffic_history_for_reused_name": MagicMock(),
        "apply_owner_access_until_to_config": MagicMock(return_value={}),
        "find_sync_group_for_primary": MagicMock(return_value=None),
    }
    with patch.multiple("app.services.config_provisioning", **patches), patch.object(
        admin_notify_service, "send_config_create"
    ) as notify_mock:
        cfg, warn = provision_config(
            db,
            node=other,
            client_name="bob",
            vpn_type=VpnType.wireguard,
            owner=owner,
            actor=actor,
            notify=False,
        )

    assert cfg.node_id == other.id
    assert warn is None
    adapter.add_wireguard_client.assert_called_once_with("bob")
    adapter.add_openvpn_client.assert_not_called()
    notify_mock.assert_not_called()


def test_provision_config_notify_true_sends_admin_notify(db, monkeypatch):
    other = _node(db, name="other", port=9101)
    owner = _user(db, username="ivan", role=UserRole.user)
    actor = _user(db, username="admin", role=UserRole.admin)

    adapter = MagicMock()
    monkeypatch.setattr("app.services.config_provisioning.get_adapter_for_node", lambda n: adapter)

    patches = {
        "recreate_openvpn_profiles_after_admin_change": MagicMock(),
        "load_node_remote_hosts": MagicMock(return_value=[]),
        "refresh_config_cert_expiry": MagicMock(),
        "purge_traffic_history_for_reused_name": MagicMock(),
        "apply_owner_access_until_to_config": MagicMock(return_value={}),
        "find_sync_group_for_primary": MagicMock(return_value=None),
    }
    with patch.multiple("app.services.config_provisioning", **patches), patch.object(
        admin_notify_service, "send_config_create"
    ) as notify_mock:
        provision_config(
            db,
            node=other,
            client_name="bob",
            vpn_type=VpnType.wireguard,
            owner=owner,
            actor=actor,
            notify=True,
        )

    notify_mock.assert_called_once()
