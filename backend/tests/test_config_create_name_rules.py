"""New clients from the web UI and the Mini App (``POST /api/configs``) follow the name rules."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.routers import configs as configs_router
from app.schemas import VpnConfigCreate


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


def _owner(db) -> User:
    user = User(username="admin", password_hash="x", role=UserRole.admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create(db, node: Node, owner: User, adapter: MagicMock, client_name: str, vpn_type: VpnType = VpnType.openvpn):
    patches = {
        "enforce_user_can_create_config": MagicMock(),
        "require_ha_primary_for_client_ops": MagicMock(),
        "_active_node_id": MagicMock(return_value=node.id),
        "require_vpn_type": MagicMock(),
        "get_feature_service": MagicMock(return_value=SimpleNamespace()),
        "enforce_can_create_vpn_type": MagicMock(),
        "get_active_adapter": MagicMock(return_value=adapter),
        "recreate_openvpn_profiles_after_admin_change": MagicMock(),
        "load_node_remote_hosts": MagicMock(return_value=[]),
        "refresh_config_cert_expiry": MagicMock(),
        "purge_traffic_history_for_reused_name": MagicMock(),
        "apply_owner_access_until_to_config": MagicMock(return_value={}),
        "find_sync_group_for_primary": MagicMock(return_value=None),
        "get_active_node": MagicMock(return_value=node),
        "get_client_timezone_from_request": MagicMock(return_value="UTC"),
        "_viewer_visibility_policy": MagicMock(return_value={}),
        "resolve_openvpn_group_for_user": MagicMock(return_value=None),
        "_local_ip_for_config": MagicMock(return_value=None),
        "_to_response": MagicMock(return_value={"ok": True}),
    }
    admin = SimpleNamespace(id=owner.id, username="admin", role=UserRole.admin)
    payload = VpnConfigCreate(client_name=client_name, vpn_type=vpn_type)
    with (
        patch.multiple(configs_router, **patches),
        patch.object(configs_router.admin_notify_service, "send_config_create"),
    ):
        return configs_router.create_config(payload, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")), db, admin)


def test_reserved_prefix_is_rejected_before_touching_the_node(db):
    node, owner = _node(db), _owner(db)
    adapter = MagicMock()

    with pytest.raises(HTTPException) as exc:
        _create(db, node, owner, adapter, "vpn-alice")

    assert exc.value.status_code == 400
    assert "«vpn-»" in exc.value.detail
    adapter.add_openvpn_client.assert_not_called()
    assert db.query(VpnConfig).count() == 0


def test_name_differing_only_by_case_is_rejected(db):
    node, owner = _node(db), _owner(db)
    db.add(VpnConfig(node_id=node.id, client_name="Ivan", vpn_type=VpnType.wireguard, owner_id=owner.id))
    db.commit()
    adapter = MagicMock()

    with pytest.raises(HTTPException) as exc:
        _create(db, node, owner, adapter, "ivan", VpnType.wireguard)

    assert exc.value.status_code == 400
    assert "«Ivan»" in exc.value.detail
    adapter.add_wireguard_client.assert_not_called()


def test_same_name_for_another_protocol_is_created(db):
    node, owner = _node(db), _owner(db)
    db.add(VpnConfig(node_id=node.id, client_name="ivan", vpn_type=VpnType.wireguard, owner_id=owner.id))
    db.commit()
    adapter = MagicMock()

    assert _create(db, node, owner, adapter, "ivan", VpnType.openvpn) == {"ok": True}

    adapter.add_openvpn_client.assert_called_once_with("ivan", 3650)
