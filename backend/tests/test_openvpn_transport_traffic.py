"""OpenVPN UDP/TCP transport protocol_type mapping and consumed-traffic filters."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants.public_routes import DEFAULT_OPENVPN_GROUP
from app.database import Base
from app.models import UserTrafficSample, UserTrafficStatProtocol
from app.services.openvpn_group import (
    OPENVPN_PROTOCOL_ALL,
    OPENVPN_PROTOCOL_TCP,
    OPENVPN_PROTOCOL_UDP,
    WIREGUARD_PROTOCOL,
    protocol_types_for_openvpn_group,
)
from app.services.traffic.collector import protocol_type_from_profile
from app.services.traffic_limit import get_client_consumed_traffic_bytes

NODE_ID = 1


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


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("antizapret-udp", "openvpn-udp"),
        ("vpn-udp", "openvpn-udp"),
        ("antizapret-tcp", "openvpn-tcp"),
        ("vpn-tcp", "openvpn-tcp"),
        ("antizapret-wg", "wireguard"),
        ("vpn-wg", "wireguard"),
        ("antizapret", "openvpn"),
        ("vpn", "openvpn"),
        ("", "openvpn"),
        (None, "openvpn"),
    ],
)
def test_protocol_type_from_profile(profile, expected):
    assert protocol_type_from_profile(profile) == expected


@pytest.mark.parametrize(
    ("group", "expected"),
    [
        ("GROUP_UDP", frozenset({"openvpn-udp"})),
        ("GROUP_TCP", frozenset({"openvpn-tcp"})),
        (DEFAULT_OPENVPN_GROUP, frozenset({"openvpn", "openvpn-udp", "openvpn-tcp"})),
        ("GROUP_UDP\\TCP", frozenset({"openvpn", "openvpn-udp", "openvpn-tcp"})),
        ("unknown", frozenset({"openvpn", "openvpn-udp", "openvpn-tcp"})),
        (None, frozenset({"openvpn", "openvpn-udp", "openvpn-tcp"})),
    ],
)
def test_protocol_types_for_openvpn_group(group, expected):
    assert protocol_types_for_openvpn_group(group) == expected


def _add_stat(db, *, common_name: str, protocol_type: str, received: int, sent: int = 0) -> None:
    db.add(
        UserTrafficStatProtocol(
            node_id=NODE_ID,
            common_name=common_name,
            protocol_type=protocol_type,
            total_received=received,
            total_sent=sent,
            total_sessions=1,
        )
    )


def test_consumed_filters_by_transport(db):
    _add_stat(db, common_name="Alice", protocol_type=OPENVPN_PROTOCOL_UDP, received=100, sent=50)
    _add_stat(db, common_name="Alice", protocol_type=OPENVPN_PROTOCOL_TCP, received=200, sent=25)
    _add_stat(db, common_name="Alice", protocol_type="openvpn", received=10, sent=5)
    _add_stat(db, common_name="Alice", protocol_type="wireguard", received=999, sent=1)
    db.commit()

    assert (
        get_client_consumed_traffic_bytes(
            db, client_name="Alice", node_id=NODE_ID, protocol_types={OPENVPN_PROTOCOL_UDP}
        )
        == 150
    )
    assert (
        get_client_consumed_traffic_bytes(
            db, client_name="Alice", node_id=NODE_ID, protocol_types={OPENVPN_PROTOCOL_TCP}
        )
        == 225
    )
    assert (
        get_client_consumed_traffic_bytes(
            db, client_name="Alice", node_id=NODE_ID, protocol_types=OPENVPN_PROTOCOL_ALL
        )
        == 390
    )
    assert (
        get_client_consumed_traffic_bytes(
            db, client_name="Alice", node_id=NODE_ID, protocol_types=WIREGUARD_PROTOCOL
        )
        == 1000
    )


def test_consumed_period_filters_by_transport(db):
    now = datetime.utcnow()
    db.add(
        UserTrafficSample(
            node_id=NODE_ID,
            common_name="Bob",
            network_type="vpn",
            protocol_type=OPENVPN_PROTOCOL_UDP,
            delta_received=40,
            delta_sent=10,
            created_at=now,
        )
    )
    db.add(
        UserTrafficSample(
            node_id=NODE_ID,
            common_name="Bob",
            network_type="vpn",
            protocol_type=OPENVPN_PROTOCOL_TCP,
            delta_received=70,
            delta_sent=5,
            created_at=now,
        )
    )
    db.add(
        UserTrafficSample(
            node_id=NODE_ID,
            common_name="Bob",
            network_type="vpn",
            protocol_type="wireguard",
            delta_received=500,
            delta_sent=0,
            created_at=now,
        )
    )
    db.commit()

    assert (
        get_client_consumed_traffic_bytes(
            db,
            client_name="Bob",
            node_id=NODE_ID,
            period_days=1,
            protocol_types={OPENVPN_PROTOCOL_UDP},
        )
        == 50
    )
    assert (
        get_client_consumed_traffic_bytes(
            db,
            client_name="Bob",
            node_id=NODE_ID,
            period_days=1,
            protocol_types=OPENVPN_PROTOCOL_ALL,
        )
        == 125
    )
    assert (
        get_client_consumed_traffic_bytes(
            db,
            client_name="Bob",
            node_id=NODE_ID,
            period_days=1,
            protocol_types=WIREGUARD_PROTOCOL,
        )
        == 500
    )
