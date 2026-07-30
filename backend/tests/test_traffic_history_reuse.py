"""Traffic left by a deleted client must not be inherited when its name is reused."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    TrafficSessionState,
    UserTrafficSample,
    UserTrafficStatProtocol,
    VpnConfig,
    VpnType,
)
from app.services.traffic.maintenance import purge_traffic_history_for_reused_name
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


def _seed_traffic(db, common_name: str, *, node_id: int = NODE_ID) -> None:
    db.add(
        UserTrafficStatProtocol(
            node_id=node_id,
            common_name=common_name,
            protocol_type="openvpn",
            total_received=1_000,
            total_sent=2_000,
            total_sessions=1,
        )
    )
    db.add(
        UserTrafficSample(
            node_id=node_id,
            common_name=common_name,
            network_type="antizapret",
            protocol_type="openvpn",
            delta_received=1_000,
            delta_sent=2_000,
            created_at=datetime(2026, 7, 22, 15, 10, 55),
        )
    )
    db.add(
        TrafficSessionState(
            node_id=node_id,
            session_key=f"antizapret-udp|{common_name}|{node_id}",
            profile="antizapret-udp",
            common_name=common_name,
            connected_since_ts=1_784_733_015,
            is_active=False,
        )
    )
    db.commit()


def _add_config(db, client_name: str, vpn_type: VpnType = VpnType.openvpn) -> VpnConfig:
    config = VpnConfig(
        node_id=NODE_ID,
        client_name=client_name,
        vpn_type=vpn_type,
        owner_id=1,
    )
    db.add(config)
    db.commit()
    return config


def test_purge_removes_history_of_deleted_client(db):
    _seed_traffic(db, "Chernov")

    removed = purge_traffic_history_for_reused_name(db, node_id=NODE_ID, client_name="Chernov")
    db.commit()

    assert removed == 3
    assert db.query(UserTrafficStatProtocol).count() == 0
    assert db.query(UserTrafficSample).count() == 0
    assert db.query(TrafficSessionState).count() == 0


def test_new_client_does_not_inherit_consumed_traffic(db):
    _seed_traffic(db, "Chernov")
    assert get_client_consumed_traffic_bytes(db, client_name="Chernov", node_id=NODE_ID) == 3_000

    purge_traffic_history_for_reused_name(db, node_id=NODE_ID, client_name="Chernov")
    _add_config(db, "Chernov")

    assert get_client_consumed_traffic_bytes(db, client_name="Chernov", node_id=NODE_ID) == 0


def test_purge_keeps_history_when_name_still_in_use(db):
    """Same person adding a second protocol keeps their usage."""
    _seed_traffic(db, "Chernov")
    _add_config(db, "Chernov", VpnType.openvpn)

    removed = purge_traffic_history_for_reused_name(db, node_id=NODE_ID, client_name="Chernov")

    assert removed == 0
    assert db.query(UserTrafficStatProtocol).count() == 1
    assert get_client_consumed_traffic_bytes(db, client_name="Chernov", node_id=NODE_ID) == 3_000


def test_purge_matches_name_case_insensitively(db):
    _seed_traffic(db, "Chernov")

    removed = purge_traffic_history_for_reused_name(db, node_id=NODE_ID, client_name="  chernov ")
    db.commit()

    assert removed == 3
    assert db.query(UserTrafficStatProtocol).count() == 0


def test_purge_leaves_other_clients_and_nodes_untouched(db):
    _seed_traffic(db, "Chernov")
    _seed_traffic(db, "Alina")
    _seed_traffic(db, "Chernov", node_id=2)

    purge_traffic_history_for_reused_name(db, node_id=NODE_ID, client_name="Chernov")
    db.commit()

    remaining = {(row.node_id, row.common_name) for row in db.query(UserTrafficStatProtocol).all()}
    assert remaining == {(NODE_ID, "Alina"), (2, "Chernov")}


def test_purge_ignores_blank_name(db):
    _seed_traffic(db, "Chernov")

    assert purge_traffic_history_for_reused_name(db, node_id=NODE_ID, client_name="  ") == 0
    assert db.query(UserTrafficStatProtocol).count() == 1
