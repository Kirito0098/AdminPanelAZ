"""Chart / reset scopes must accept and isolate amneziawg2 traffic."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import TrafficSessionState, UserTrafficSample, UserTrafficStatProtocol
from app.services.traffic.chart import fetch_traffic_chart
from app.services.traffic.collector import TrafficCollectorService
from app.services.traffic.maintenance import (
    TrafficMaintenanceService,
    _profile_matches_protocol_scope,
    normalize_traffic_protocol_scope,
)

NODE_ID = 1
CLIENT = "ivan"


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


def _add_sample(db, *, protocol: str, delta: int, hours_ago: float = 1.0, network: str = "vpn") -> None:
    db.add(
        UserTrafficSample(
            node_id=NODE_ID,
            common_name=CLIENT,
            network_type=network,
            protocol_type=protocol,
            delta_received=delta,
            delta_sent=0,
            created_at=datetime.utcnow() - timedelta(hours=hours_ago),
        )
    )


def _add_session(db, *, profile: str, protocol_hint: str) -> None:
    db.add(
        TrafficSessionState(
            node_id=NODE_ID,
            session_key=f"{profile}|{CLIENT}|{protocol_hint}",
            profile=profile,
            common_name=CLIENT,
            connected_since_ts=0,
            is_active=False,
        )
    )


def _add_stat(db, *, protocol: str, received: int = 100) -> None:
    db.add(
        UserTrafficStatProtocol(
            node_id=NODE_ID,
            common_name=CLIENT,
            protocol_type=protocol,
            total_received=received,
            total_sent=0,
            total_sessions=1,
        )
    )


def test_normalize_scope_accepts_amneziawg2():
    assert normalize_traffic_protocol_scope("amneziawg2") == "amneziawg2"
    assert normalize_traffic_protocol_scope("AmneziaWG2") == "amneziawg2"
    assert normalize_traffic_protocol_scope("bogus") == "all"
    assert normalize_traffic_protocol_scope("wireguard") == "wireguard"


def test_profile_matches_amneziawg2_scope():
    assert _profile_matches_protocol_scope("antizapret-awg2", "amneziawg2")
    assert _profile_matches_protocol_scope("vpn-awg2", "amneziawg2")
    assert not _profile_matches_protocol_scope("antizapret-wg", "amneziawg2")
    assert not _profile_matches_protocol_scope("antizapret-udp", "amneziawg2")
    assert not _profile_matches_protocol_scope("antizapret-awg2", "wireguard")
    assert not _profile_matches_protocol_scope("antizapret-awg2", "openvpn")
    assert _profile_matches_protocol_scope("antizapret-wg", "wireguard")
    assert _profile_matches_protocol_scope("antizapret-udp", "openvpn")


def test_chart_includes_amneziawg2_series_and_filter(db):
    _add_sample(db, protocol="openvpn", delta=10)
    _add_sample(db, protocol="wireguard", delta=20)
    _add_sample(db, protocol="amneziawg2", delta=40)
    db.commit()

    all_chart = fetch_traffic_chart(db, NODE_ID, CLIENT, "7d", "all")
    assert all_chart["protocol_filter"] == "all"
    assert sum(all_chart["openvpn_bytes"]) == 10
    assert sum(all_chart["wireguard_bytes"]) == 20
    assert sum(all_chart["amneziawg2_bytes"]) == 40
    assert all_chart["total"] == 70

    awg2_only = fetch_traffic_chart(db, NODE_ID, CLIENT, "7d", "amneziawg2")
    assert awg2_only["protocol_filter"] == "amneziawg2"
    assert sum(awg2_only["amneziawg2_bytes"]) == 40
    assert sum(awg2_only["openvpn_bytes"]) == 0
    assert sum(awg2_only["wireguard_bytes"]) == 0
    assert awg2_only["total"] == 40

    wg_only = fetch_traffic_chart(db, NODE_ID, CLIENT, "7d", "wireguard")
    assert sum(wg_only["wireguard_bytes"]) == 20
    assert sum(wg_only["amneziawg2_bytes"]) == 0
    assert wg_only["total"] == 20


def test_chart_accepts_amneziawg2_filter_token(db):
    _add_sample(db, protocol="amneziawg2", delta=5)
    db.commit()
    result = fetch_traffic_chart(db, NODE_ID, CLIENT, "7d", "AMNEZIAWG2")
    assert result["protocol_filter"] == "amneziawg2"
    assert sum(result["amneziawg2_bytes"]) == 5


def test_delete_persisted_rows_amneziawg2_scope_leaves_others(db):
    _add_sample(db, protocol="openvpn", delta=1)
    _add_sample(db, protocol="wireguard", delta=2)
    _add_sample(db, protocol="amneziawg2", delta=3)
    _add_session(db, profile="antizapret-udp", protocol_hint="ovpn")
    _add_session(db, profile="antizapret-wg", protocol_hint="wg")
    _add_session(db, profile="antizapret-awg2", protocol_hint="awg2")
    db.commit()

    service = TrafficMaintenanceService(db, NODE_ID)
    result = service.delete_persisted_traffic_rows_by_scope("amneziawg2")
    db.commit()

    assert result["scope"] == "amneziawg2"
    assert result["deleted_samples"] == 1
    assert result["deleted_sessions"] == 1

    protocols = {row.protocol_type for row in db.query(UserTrafficSample).all()}
    assert protocols == {"openvpn", "wireguard"}
    profiles = {row.profile for row in db.query(TrafficSessionState).all()}
    assert profiles == {"antizapret-udp", "antizapret-wg"}


def test_openvpn_reset_does_not_delete_amneziawg2_sessions(db):
    _add_sample(db, protocol="openvpn", delta=1)
    _add_sample(db, protocol="amneziawg2", delta=9)
    _add_session(db, profile="vpn-udp", protocol_hint="ovpn")
    _add_session(db, profile="vpn-awg2", protocol_hint="awg2")
    db.commit()

    service = TrafficMaintenanceService(db, NODE_ID)
    result = service.delete_persisted_traffic_rows_by_scope("openvpn")
    db.commit()

    assert result["deleted_samples"] == 1
    assert result["deleted_sessions"] == 1
    assert db.query(UserTrafficSample).filter_by(protocol_type="amneziawg2").count() == 1
    assert db.query(TrafficSessionState).filter_by(profile="vpn-awg2").count() == 1


def test_collector_reset_traffic_amneziawg2_scope(db):
    _add_sample(db, protocol="openvpn", delta=1)
    _add_sample(db, protocol="amneziawg2", delta=7)
    _add_stat(db, protocol="openvpn", received=1)
    _add_stat(db, protocol="amneziawg2", received=7)
    db.commit()

    collector = TrafficCollectorService(db, NODE_ID)
    deleted = collector.reset_traffic(scope="amneziawg2")

    assert deleted == 1
    assert db.query(UserTrafficSample).count() == 1
    assert db.query(UserTrafficSample).one().protocol_type == "openvpn"
    assert db.query(UserTrafficStatProtocol).count() == 1
    assert db.query(UserTrafficStatProtocol).one().protocol_type == "openvpn"
