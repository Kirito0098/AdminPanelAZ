"""can_manage_configs enforcement on delete, and cert-days normalisation for role=user."""

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
from app.services.self_service import USER_OPENVPN_CERT_DAYS, awg2_ttl_for_actor, openvpn_cert_days_for_actor


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


def test_owner_without_manage_flag_gets_clear_403_on_delete(db, monkeypatch):
    node = _node(db)
    config = VpnConfig(node_id=node.id, client_name="alice", vpn_type=VpnType.wireguard, owner_id=7)
    db.add(config)
    db.commit()
    monkeypatch.setattr(configs_router, "_get_config_for_active_node", lambda _db, _id: config)
    user = SimpleNamespace(id=7, role=UserRole.user, can_manage_configs=False)

    with pytest.raises(HTTPException) as exc:
        configs_router.delete_config(config.id, SimpleNamespace(), db, user)

    assert exc.value.status_code == 403
    assert "Управление" in exc.value.detail


def _create_openvpn(db, node: Node, actor, adapter: MagicMock, cert_expire_days: int):
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
    payload = VpnConfigCreate(client_name="alice", vpn_type=VpnType.openvpn, cert_expire_days=cert_expire_days)
    with (
        patch.multiple(configs_router, **patches),
        patch.object(configs_router.admin_notify_service, "send_config_create"),
    ):
        configs_router.create_config(payload, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")), db, actor)


def test_user_create_ignores_requested_cert_days(db):
    node = _node(db)
    db.add(User(id=5, username="u", password_hash="x", role=UserRole.user))
    db.commit()
    actor = SimpleNamespace(id=5, username="u", role=UserRole.user, can_manage_configs=False)
    adapter = MagicMock()

    _create_openvpn(db, node, actor, adapter, 30)

    adapter.add_openvpn_client.assert_called_once_with("alice", USER_OPENVPN_CERT_DAYS)
    assert db.query(VpnConfig).one().cert_expire_days == USER_OPENVPN_CERT_DAYS


def test_admin_create_keeps_requested_cert_days(db):
    node = _node(db)
    db.add(User(id=1, username="a", password_hash="x", role=UserRole.admin))
    db.commit()
    actor = SimpleNamespace(id=1, username="a", role=UserRole.admin)
    adapter = MagicMock()

    _create_openvpn(db, node, actor, adapter, 90)

    adapter.add_openvpn_client.assert_called_once_with("alice", 90)
    assert db.query(VpnConfig).one().cert_expire_days == 90


def test_actor_helpers_normalise_for_user_only():
    admin = SimpleNamespace(role=UserRole.admin)
    user = SimpleNamespace(role=UserRole.user)
    assert openvpn_cert_days_for_actor(admin, 90) == 90
    assert openvpn_cert_days_for_actor(admin, None) == USER_OPENVPN_CERT_DAYS
    assert openvpn_cert_days_for_actor(user, 30) == USER_OPENVPN_CERT_DAYS
    assert awg2_ttl_for_actor(admin, "7d") == "7d"
    assert awg2_ttl_for_actor(user, "7d") is None
