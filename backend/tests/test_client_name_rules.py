"""Name rules for new VPN clients: reserved AntiZapret prefixes and case-only twins."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.services.client_names import validate_new_client_name


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


def _config(db, node: Node, owner: User, name: str, vpn_type: VpnType) -> VpnConfig:
    config = VpnConfig(node_id=node.id, client_name=name, vpn_type=vpn_type, owner_id=owner.id)
    db.add(config)
    db.commit()
    return config


@pytest.mark.parametrize("name", ["vpn-alice", "antizapret-bob", "VPN-carol", "Antizapret-dan"])
def test_rejects_reserved_prefixes(db, name):
    node = _node(db)

    with pytest.raises(ValueError, match="не может начинаться"):
        validate_new_client_name(db, node_id=node.id, client_name=name)


@pytest.mark.parametrize("name", ["vpnalice", "my-vpn-1", "vpn", "antizapret"])
def test_allows_names_without_reserved_prefix(db, name):
    node = _node(db)

    validate_new_client_name(db, node_id=node.id, client_name=name)


def test_rejects_name_differing_only_by_case(db):
    node, owner = _node(db), _owner(db)
    _config(db, node, owner, "Ivan", VpnType.wireguard)

    with pytest.raises(ValueError, match="«Ivan»"):
        validate_new_client_name(db, node_id=node.id, client_name="ivan")


def test_case_twin_of_another_protocol_is_rejected_too(db):
    node, owner = _node(db), _owner(db)
    _config(db, node, owner, "Ivan", VpnType.openvpn)

    with pytest.raises(ValueError, match="только регистром"):
        validate_new_client_name(db, node_id=node.id, client_name="IVAN")


def test_allows_exact_name_of_another_protocol(db):
    node, owner = _node(db), _owner(db)
    _config(db, node, owner, "ivan", VpnType.wireguard)

    validate_new_client_name(db, node_id=node.id, client_name="ivan")


def test_case_rule_is_per_node(db):
    owner = _owner(db)
    node_a = _node(db, name="a", port=9100)
    node_b = _node(db, name="b", port=9101)
    _config(db, node_a, owner, "Ivan", VpnType.wireguard)

    validate_new_client_name(db, node_id=node_b.id, client_name="ivan")
