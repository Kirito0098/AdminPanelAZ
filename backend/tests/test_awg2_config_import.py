from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.services.config_import import import_clients_from_disk


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_node(db, *, name: str = "node-1", port: int = 9100) -> Node:
    node = Node(
        name=name,
        host="127.0.0.1",
        port=port,
        api_key_hash="hash",
        api_key_encrypted="enc",
        status=NodeStatus.unknown,
        is_local=False,
        node_kind="vpn",
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _make_owner(db, *, username: str = "admin") -> User:
    user = User(username=username, password_hash="hash", role=UserRole.admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_import_awg2_and_does_not_mark_stale_as_wg(db):
    node = _make_node(db)
    owner = _make_owner(db)
    db.add(
        VpnConfig(
            node_id=node.id,
            client_name="ivan",
            vpn_type=VpnType.amneziawg2,
            owner_id=owner.id,
        )
    )
    db.add(
        VpnConfig(
            node_id=node.id,
            client_name="wire-orphan",
            vpn_type=VpnType.wireguard,
            owner_id=owner.id,
        )
    )
    db.commit()

    adapter = MagicMock()
    adapter.list_openvpn_clients.return_value = []
    adapter.list_wireguard_clients.return_value = []
    adapter.list_amneziawg2_clients.return_value = ["ivan", "olga"]

    with patch("app.services.config_import.get_adapter_for_node", return_value=adapter):
        result = import_clients_from_disk(db, node, owner.id)

    assert result.imported == 1
    assert result.removed == 1
    assert db.query(VpnConfig).filter_by(node_id=node.id, client_name="ivan", vpn_type=VpnType.amneziawg2).count() == 1
    assert db.query(VpnConfig).filter_by(node_id=node.id, client_name="olga", vpn_type=VpnType.amneziawg2).count() == 1
    assert db.query(VpnConfig).filter_by(node_id=node.id, client_name="wire-orphan", vpn_type=VpnType.wireguard).count() == 0
    adapter.list_amneziawg2_clients.assert_called_once_with()


def test_import_awg2_probe_failure_soft_fails(db):
    node = _make_node(db)
    owner = _make_owner(db)
    adapter = MagicMock()
    adapter.list_openvpn_clients.return_value = []
    adapter.list_wireguard_clients.return_value = ["bob"]
    adapter.list_amneziawg2_clients.side_effect = HTTPException(status_code=404, detail="missing")

    with patch("app.services.config_import.get_adapter_for_node", return_value=adapter):
        result = import_clients_from_disk(db, node, owner.id)

    assert result.imported == 1
    assert result.removed == 0
    adapter.list_amneziawg2_clients.assert_called_once_with()
