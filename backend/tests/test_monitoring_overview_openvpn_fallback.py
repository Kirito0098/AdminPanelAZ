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
