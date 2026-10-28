"""OpenVPN cards must not go offline when only the DB session fallback is available."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, TrafficSessionState
from app.services import monitoring_overview


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    try:
        yield make
    finally:
        engine.dispose()


def _session(node_id: int, profile: str, name: str, *, active: bool = True) -> TrafficSessionState:
    return TrafficSessionState(
        node_id=node_id,
        session_key=f"{profile}:{name}",
        profile=profile,
        common_name=name,
        real_address="203.0.113.7:1194",
        virtual_address="10.8.0.5",
        is_active=active,
    )


def test_fallback_uses_only_active_openvpn_sessions_of_the_node(factory):
    with factory() as db:
        db.add_all(
            [
                Node(id=1, name="1Cent-EE", host="h1", is_local=True, status=NodeStatus.online),
                Node(id=2, name="2Cent-EE", host="h2", is_local=False, status=NodeStatus.online),
            ]
        )
        db.commit()
        db.add_all(
            [
                _session(1, "antizapret-udp", "alice"),
                _session(1, "antizapret-wg", "bob"),
                _session(1, "wireguard", "carol"),
                _session(1, "antizapret-tcp", "gone", active=False),
                _session(2, "antizapret-udp", "other-node"),
            ]
        )
        db.commit()

        clients = monitoring_overview._openvpn_clients_from_sessions(db, 1)

    assert [client.common_name for client in clients] == ["alice"]
    assert clients[0].data_source == "db_fallback"
    assert clients[0].virtual_address == "10.8.0.5"


def test_node_overview_marks_the_db_fallback_source(factory, monkeypatch):
    with factory() as db:
        node = Node(id=1, name="1Cent-EE", host="h1", is_local=True, status=NodeStatus.online)
        db.add(node)
        db.commit()
        db.add(_session(1, "antizapret-udp", "alice"))
        db.commit()

        adapter = SimpleNamespace(
            get_openvpn_status_snapshot=lambda: ([], "none"),
            parse_wireguard_status=lambda: [],
            get_service_status=lambda: [],
            get_server_ip=lambda: "203.0.113.10",
        )
        monkeypatch.setattr(monitoring_overview, "get_adapter_for_node", lambda _node: adapter)
        monkeypatch.setattr(monitoring_overview, "is_awg2_enabled", lambda _db: False)

        overview = monitoring_overview.build_monitoring_overview_for_node(db, node)

    assert overview.openvpn_data_source == "db_fallback"
    assert [client.common_name for client in overview.openvpn_clients] == ["alice"]


def test_federated_collect_uses_db_fallback_when_socket_empty(factory, monkeypatch):
    """Clients cards use scope=all; without fallback OVPN looked offline while AWG2 worked."""
    with factory() as db:
        node = Node(id=1, name="ha-primary", host="h1", is_local=True, status=NodeStatus.online)
        db.add(node)
        db.commit()
        db.add(_session(1, "antizapret-udp", "Keenetic_Bogachevs"))
        db.commit()

        adapter = SimpleNamespace(
            get_openvpn_status_snapshot=lambda: ([], "none"),
            parse_wireguard_status=lambda: [],
            get_service_status=lambda: [],
            get_server_ip=lambda: "203.0.113.10",
            get_antizapret_settings=lambda: {},
        )
        monkeypatch.setattr(monitoring_overview, "get_adapter_for_node", lambda _node: adapter)
        monkeypatch.setattr(monitoring_overview, "is_awg2_enabled", lambda _db: False)
        monkeypatch.setattr(monitoring_overview, "_load_awg2_peers_for_node", lambda *_a, **_k: [])
        monkeypatch.setattr(monitoring_overview, "extract_cidr_routes_count", lambda *_a, **_k: None)
        monkeypatch.setattr(monitoring_overview, "is_vpn_node", lambda _n: True)

        payloads = monitoring_overview._collect_nodes_monitoring_data(db)

    assert len(payloads) == 1
    names = [c.common_name for c in payloads[0]["ovpn_clients"]]
    assert names == ["Keenetic_Bogachevs"]
    assert payloads[0]["ovpn_clients"][0].data_source == "db_fallback"


def test_merge_keeps_socket_clients_and_adds_session_only(factory):
    from app.schemas import OpenVpnClient

    with factory() as db:
        db.add(Node(id=1, name="n1", host="h1", is_local=True, status=NodeStatus.online))
        db.commit()
        db.add_all(
            [
                _session(1, "antizapret-udp", "from_socket_and_sess"),
                _session(1, "vpn-udp", "only_session"),
            ]
        )
        db.commit()

        socket_clients = [
            OpenVpnClient(
                common_name="from_socket_and_sess",
                real_address="1.1.1.1:1",
                virtual_address="10.8.0.2",
                bytes_received=10,
                bytes_sent=10,
                connected_since="",
                connected_since_ts=0,
                profile="antizapret-udp",
                data_source="management_socket",
            ),
            OpenVpnClient(
                common_name="only_socket",
                real_address="1.1.1.2:1",
                virtual_address="10.8.0.3",
                bytes_received=1,
                bytes_sent=1,
                connected_since="",
                connected_since_ts=0,
                profile="antizapret-udp",
                data_source="management_socket",
            ),
        ]
        merged = monitoring_overview._merge_openvpn_status_with_sessions(db, 1, socket_clients)

    names = {c.common_name for c in merged}
    assert names == {"from_socket_and_sess", "only_socket", "only_session"}
