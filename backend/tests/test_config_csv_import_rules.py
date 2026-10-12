"""CSV import rows follow the client name rules and the 1–3650 certificate validity range."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.services import config_csv_ops


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


def _import(db, node: Node, owner: User, adapter: MagicMock, **row: str) -> dict:
    with (
        patch.object(config_csv_ops, "require_vpn_type"),
        patch.object(config_csv_ops, "get_feature_service", return_value=SimpleNamespace()),
        patch.object(config_csv_ops, "get_active_adapter", return_value=adapter),
        patch.object(config_csv_ops, "refresh_config_cert_expiry"),
        patch.object(config_csv_ops, "purge_traffic_history_for_reused_name"),
        patch.object(config_csv_ops, "maybe_replicate_create"),
        patch("app.services.user_subscription.apply_owner_access_until_to_config", return_value={}),
        patch("app.services.user_subscription.replicate_inherited_access_until"),
    ):
        return config_csv_ops._import_single_row(
            db,
            row={"_line": "2", **row},
            node_id=node.id,
            default_owner_id=owner.id,
            owner_by_username={},
            actor_username="admin",
        )


@pytest.mark.parametrize("days", ["0", "-5", "3651"])
def test_cert_days_out_of_range_are_rejected(db, days):
    node, owner = _node(db), _owner(db)
    adapter = MagicMock()

    result = _import(db, node, owner, adapter, client_name="mira", vpn_type="openvpn", cert_expire_days=days)

    assert result["ok"] is False
    assert result["error"] == "cert_expire_days должен быть от 1 до 3650"
    adapter.add_openvpn_client.assert_not_called()
    assert db.query(VpnConfig).count() == 0


def test_cert_days_upper_bound_is_accepted(db):
    node, owner = _node(db), _owner(db)
    adapter = MagicMock()

    result = _import(db, node, owner, adapter, client_name="mira", vpn_type="openvpn", cert_expire_days="3650")

    assert result["ok"] is True
    adapter.add_openvpn_client.assert_called_once_with("mira", 3650)


def test_reserved_prefix_is_rejected(db):
    node, owner = _node(db), _owner(db)
    adapter = MagicMock()

    result = _import(db, node, owner, adapter, client_name="antizapret-mira", vpn_type="wireguard")

    assert result["ok"] is False
    assert "«antizapret-»" in result["error"]
    adapter.add_wireguard_client.assert_not_called()


def test_case_only_twin_is_rejected(db):
    node, owner = _node(db), _owner(db)
    db.add(VpnConfig(node_id=node.id, client_name="Mira", vpn_type=VpnType.openvpn, owner_id=owner.id))
    db.commit()
    adapter = MagicMock()

    result = _import(db, node, owner, adapter, client_name="mira", vpn_type="openvpn")

    assert result["ok"] is False
    assert "«Mira»" in result["error"]
    adapter.add_openvpn_client.assert_not_called()
