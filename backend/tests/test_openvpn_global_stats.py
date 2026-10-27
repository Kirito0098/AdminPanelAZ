"""OpenVPN GLOBAL_STATS (DCO, queue) must reach the panel overview."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus
from app.services import monitoring_overview
from app.services.openvpn_management import parse_global_stats

COMMA_RAW = (
    "TITLE,OpenVPN 2.7.6\n"
    "GLOBAL_STATS,Max bcast/mcast queue length,0\n"
    "GLOBAL_STATS,dco_enabled,1\n"
    "END\n"
)
TAB_RAW = "GLOBAL_STATS\tdco_enabled\t1\nGLOBAL_STATS\tMax bcast/mcast queue length\t3\nEND\n"


def test_global_stats_are_parsed_from_comma_status():
    stats = parse_global_stats(COMMA_RAW)

    assert stats["dco_enabled"] is True
    assert stats["max_bcast_mcast_queue"] == 0


def test_global_stats_are_parsed_from_tab_status():
    stats = parse_global_stats(TAB_RAW)

    assert stats["dco_enabled"] is True
    assert stats["max_bcast_mcast_queue"] == 3


def test_global_stats_are_none_without_the_rows():
    stats = parse_global_stats("TITLE,OpenVPN\nEND\n")

    assert stats == {"dco_enabled": None, "max_bcast_mcast_queue": None}


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    try:
        yield make
    finally:
        engine.dispose()


def test_node_overview_exposes_global_stats(factory, monkeypatch):
    with factory() as db:
        node = Node(id=1, name="1Cent-EE", host="h", is_local=True, status=NodeStatus.online)
        db.add(node)
        db.commit()

        adapter = SimpleNamespace(
            get_openvpn_status_snapshot=lambda: ([], "none"),
            get_openvpn_global_stats=lambda: {"dco_enabled": True, "max_bcast_mcast_queue": 2},
            parse_wireguard_status=lambda: [],
            get_service_status=lambda: [],
            get_server_ip=lambda: "203.0.113.10",
        )
        monkeypatch.setattr(monitoring_overview, "get_adapter_for_node", lambda _node: adapter)
        monkeypatch.setattr(monitoring_overview, "is_awg2_enabled", lambda _db: False)

        overview = monitoring_overview.build_monitoring_overview_for_node(db, node)

    assert overview.openvpn_global_stats is not None
    assert overview.openvpn_global_stats.dco_enabled is True
    assert overview.openvpn_global_stats.max_bcast_mcast_queue == 2


def test_node_overview_survives_an_old_agent_without_global_stats(factory, monkeypatch):
    with factory() as db:
        node = Node(id=1, name="1Cent-EE", host="h", is_local=True, status=NodeStatus.online)
        db.add(node)
        db.commit()

        def _boom():
            raise RuntimeError("404 Not Found")

        adapter = SimpleNamespace(
            get_openvpn_status_snapshot=lambda: ([], "none"),
            get_openvpn_global_stats=_boom,
            parse_wireguard_status=lambda: [],
            get_service_status=lambda: [],
            get_server_ip=lambda: "203.0.113.10",
        )
        monkeypatch.setattr(monitoring_overview, "get_adapter_for_node", lambda _node: adapter)
        monkeypatch.setattr(monitoring_overview, "is_awg2_enabled", lambda _db: False)

        overview = monitoring_overview.build_monitoring_overview_for_node(db, node)

    assert overview.openvpn_global_stats is None
