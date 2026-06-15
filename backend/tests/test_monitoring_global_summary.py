"""Tests for global dashboard summary and federated monitoring cache."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeResourceSample, NodeStatus, User, UserRole
from app.schemas import MonitoringService, OpenVpnClient, WireGuardPeer
from app.services import node_remote_cache
from app.services.monitoring_overview import build_global_dashboard_summary
from app.services.resource_metrics import get_latest_samples_by_node


@pytest.fixture()
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    node_a = Node(name="eu-1", host="10.0.0.1", port=9100, is_local=True, status=NodeStatus.online)
    node_b = Node(name="us-1", host="10.0.0.2", port=9100, is_local=False, status=NodeStatus.offline)
    session.add_all([node_a, node_b])
    session.commit()
    session.refresh(node_a)
    session.refresh(node_b)
    session.add(
        NodeResourceSample(
            node_id=node_a.id,
            cpu_percent=42.5,
            memory_percent=61.0,
            memory_used_mb=1000,
            memory_total_mb=8000,
            disk_percent=30.0,
            created_at=datetime.utcnow(),
        )
    )
    session.commit()
    yield session, node_a, node_b
    session.close()


def _adapter_for_node(node_name: str):
    adapter = MagicMock()
    adapter.get_server_ip.return_value = "203.0.113.1" if node_name == "eu-1" else "203.0.113.2"
    if node_name == "eu-1":
        adapter.get_openvpn_status_snapshot.return_value = (
            [
                OpenVpnClient(
                    common_name="alice",
                    real_address="1.2.3.4:1194",
                    virtual_address="10.8.0.2",
                    bytes_received=1,
                    bytes_sent=1,
                    connected_since="now",
                )
            ],
            "status_log",
        )
        adapter.parse_wireguard_status.return_value = [
            WireGuardPeer(
                interface="wg0",
                public_key="pk1",
                endpoint="5.6.7.8:51820",
                client_name="bob",
                latest_handshake="now",
            )
        ]
        adapter.get_service_status.return_value = [
            MonitoringService(name="openvpn", status="active", active=True),
            MonitoringService(name="wireguard", status="active", active=True),
        ]
    else:
        adapter.get_openvpn_status_snapshot.return_value = ([], "status_log")
        adapter.parse_wireguard_status.return_value = []
        adapter.get_service_status.return_value = [
            MonitoringService(name="openvpn", status="inactive", active=False),
        ]
    return adapter


def test_get_latest_samples_by_node_returns_most_recent(db_session):
    session, node_a, _node_b = db_session
    older = NodeResourceSample(
        node_id=node_a.id,
        cpu_percent=1.0,
        memory_percent=1.0,
        memory_used_mb=1,
        memory_total_mb=1,
        disk_percent=1.0,
        created_at=datetime(2020, 1, 1),
    )
    session.add(older)
    session.commit()

    latest = get_latest_samples_by_node(session)
    assert node_a.id in latest
    assert latest[node_a.id].cpu_percent == 42.5


def test_build_global_dashboard_summary_aggregates_nodes(db_session):
    session, node_a, node_b = db_session

    def adapter_for(node):
        return _adapter_for_node(node.name)

    with patch("app.services.monitoring_overview.get_adapter_for_node", side_effect=adapter_for):
        summary = build_global_dashboard_summary(session)

    assert summary.nodes_total == 2
    assert summary.nodes_online == 1
    assert summary.total_connected_openvpn == 1
    assert summary.total_connected_wireguard == 1
    by_name = {item.node_name: item for item in summary.nodes_summary}
    assert by_name["eu-1"].cpu_percent == 42.5
    assert by_name["eu-1"].memory_percent == 61.0
    assert by_name["eu-1"].connected_openvpn == 1
    assert by_name["us-1"].connected_openvpn == 0


def test_global_summary_api_returns_cached_payload(db_session):
    session, node_a, node_b = db_session
    from app.auth import get_current_user
    from app.database import get_db
    from app.main import app

    admin = User(username="admin", password_hash="hash", role=UserRole.admin, theme="dark")

    def override_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin
    node_remote_cache.invalidate_monitoring_overview(node_remote_cache.GLOBAL_DASHBOARD_CACHE_KEY)

    with patch("app.services.monitoring_overview.get_adapter_for_node") as get_adapter:
        get_adapter.side_effect = lambda node: _adapter_for_node(node.name)
        client = TestClient(app)
        first = client.get("/api/monitoring/global-summary")
        second = client.get("/api/monitoring/global-summary")

    app.dependency_overrides.clear()
    assert first.status_code == 200
    assert second.status_code == 200
    assert get_adapter.call_count == 2
    body = first.json()
    assert body["nodes_total"] == 2
    assert body["total_connected_openvpn"] == 1
    assert len(body["nodes_summary"]) == 2


def test_monitoring_overview_scope_all_uses_federated_cache(db_session):
    session, node_a, node_b = db_session
    from app.auth import get_current_user
    from app.database import get_db
    from app.main import app

    admin = User(username="admin", password_hash="hash", role=UserRole.admin, theme="dark")

    def override_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin
    node_remote_cache.invalidate_monitoring_overview(node_remote_cache.FEDERATED_OVERVIEW_CACHE_KEY)

    with patch("app.services.monitoring_overview.get_adapter_for_node") as get_adapter, patch(
        "app.services.monitoring_overview.get_active_node",
        return_value=node_a,
    ), patch("app.services.monitoring_overview.lookup_ips_geo", return_value={}):
        get_adapter.side_effect = lambda node: _adapter_for_node(node.name)
        client = TestClient(app)
        first = client.get("/api/monitoring/overview?scope=all")
        second = client.get("/api/monitoring/overview?scope=all")

    app.dependency_overrides.clear()
    assert first.status_code == 200
    assert second.status_code == 200
    assert get_adapter.call_count == 2
    body = first.json()
    assert body["scope"] == "all"
    assert body["nodes_total"] == 2
    assert body["nodes_summary"][0]["cpu_percent"] == 42.5
