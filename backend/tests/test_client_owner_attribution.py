"""Client → owner attribution used by NOC and traffic monitoring."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, User, UserRole, VpnConfig, VpnType
from app.schemas import OpenVpnClient, WireGuardPeer
from app.services.client_owners import (
    find_client_owner,
    load_client_owners,
    owner_fields,
    owner_fields_for_viewer,
)
from app.services.monitoring_overview import _attach_client_owners
from app.services.traffic.maintenance import TrafficMaintenanceService


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


def _seed(db):
    db.add_all(
        [
            Node(id=1, name="primary", host="127.0.0.1", is_local=True),
            Node(id=2, name="replica", host="10.0.0.2"),
            User(id=1, username="alice", password_hash="x", role=UserRole.user),
            User(id=2, username="bob", password_hash="x", role=UserRole.user),
        ]
    )
    db.add_all(
        [
            VpnConfig(node_id=1, client_name="ivan", vpn_type=VpnType.openvpn, owner_id=1),
            VpnConfig(node_id=1, client_name="ivan", vpn_type=VpnType.wireguard, owner_id=1),
            VpnConfig(node_id=1, client_name="petr", vpn_type=VpnType.openvpn, owner_id=2),
            VpnConfig(node_id=2, client_name="ivan", vpn_type=VpnType.openvpn, owner_id=1),
        ]
    )
    db.commit()


def test_load_client_owners_maps_names_per_node_case_insensitively(db):
    _seed(db)
    owners = load_client_owners(db)

    assert owners[(1, "ivan")].user_id == 1
    assert owners[(1, "ivan")].username == "alice"
    assert owners[(1, "petr")].username == "bob"
    assert owners[(2, "ivan")].username == "alice"
    assert (2, "petr") not in owners


def test_load_client_owners_is_scoped_to_given_nodes(db):
    _seed(db)

    owners = load_client_owners(db, [2])

    assert set(owners) == {(2, "ivan")}


def test_load_client_owners_with_empty_scope_returns_nothing(db):
    _seed(db)

    assert load_client_owners(db, []) == {}


def test_find_client_owner_walks_ha_node_scope(db):
    _seed(db)
    owners = load_client_owners(db, [1, 2])

    assert find_client_owner(owners, [2, 1], "IVAN").username == "alice"
    assert find_client_owner(owners, [2], "petr") is None
    assert find_client_owner(owners, [1], "") is None


def test_owner_fields_for_missing_owner_are_none():
    assert owner_fields(None) == {"owner_id": None, "owner_username": None}


def test_owner_fields_for_viewer_hides_foreign_owners_from_grantees(db):
    _seed(db)
    owner = load_client_owners(db, [1])[(1, "ivan")]

    assert owner_fields_for_viewer(owner, viewer_id=None, is_admin=True) == {
        "owner_id": 1,
        "owner_username": "alice",
    }
    assert owner_fields_for_viewer(owner, viewer_id=1, is_admin=False)["owner_username"] == "alice"
    assert owner_fields_for_viewer(owner, viewer_id=2, is_admin=False) == {
        "owner_id": None,
        "owner_username": None,
    }


def test_attach_client_owners_sets_owner_on_connections(db):
    _seed(db)
    owners = load_client_owners(db, [1])
    ovpn = OpenVpnClient(
        common_name="ivan",
        real_address="1.2.3.4:1194",
        virtual_address="10.8.0.2",
        bytes_received=1,
        bytes_sent=2,
        connected_since="2026-10-21 10:00:00",
        node_id=1,
        node_name="primary",
    )
    orphan = ovpn.model_copy(update={"common_name": "legacy", "node_id": 1})
    peer = WireGuardPeer(
        interface="antizapret",
        public_key="pk",
        client_name="petr",
        node_id=1,
        node_name="primary",
    )
    peer_without_config = peer.model_copy(update={"client_name": "nobody"})

    attached = _attach_client_owners([ovpn, orphan, peer, peer_without_config], owners)

    assert attached[0].owner_id == 1
    assert attached[0].owner_username == "alice"
    assert attached[1].owner_id is None
    assert attached[2].owner_username == "bob"
    assert attached[3].owner_username is None


def test_never_connected_rows_include_owner(db):
    _seed(db)

    rows, _summary = TrafficMaintenanceService(db, 1).get_never_connected_config_rows()

    by_name = {(row["common_name"], row["protocol_type"]): row for row in rows}
    assert by_name[("ivan", "openvpn")]["owner_id"] == 1
    assert by_name[("ivan", "openvpn")]["owner_username"] == "alice"
    assert by_name[("petr", "openvpn")]["owner_username"] == "bob"
