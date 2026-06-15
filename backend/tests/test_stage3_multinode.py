"""Tests for geo routing hint and node policy summary."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, OpenVpnAccessPolicy, User, UserRole, WgAccessPolicy
from app.services.access_policy import build_policy_summary_by_node
from app.services.geo_routing_hint import build_geo_routing_hint


@pytest.fixture()
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    eu = Node(name="eu-1", host="10.0.0.1", port=9100, is_local=True, status=NodeStatus.online)
    us = Node(name="us-1", host="10.0.0.2", port=9100, is_local=False, status=NodeStatus.online)
    session.add_all([eu, us])
    session.commit()
    session.refresh(eu)
    session.refresh(us)
    session.add(
        OpenVpnAccessPolicy(
            node_id=eu.id,
            client_name="alice",
            is_permanent_blocked=True,
        )
    )
    session.add(
        WgAccessPolicy(
            node_id=us.id,
            client_name="bob",
            traffic_limit_bytes=1_000_000,
        )
    )
    session.commit()
    yield session, eu, us
    session.close()


def test_build_policy_summary_by_node_counts_rows(db_session):
    session, eu, us = db_session
    summaries = build_policy_summary_by_node(session)
    by_name = {item["node_name"]: item for item in summaries}
    assert by_name["eu-1"]["openvpn_policies"] == 1
    assert by_name["eu-1"]["blocked_clients"] == 1
    assert by_name["us-1"]["wireguard_policies"] == 1
    assert by_name["us-1"]["traffic_limited_clients"] == 1


def test_build_geo_routing_hint_prefers_same_country(db_session):
    session, eu, _us = db_session

    adapter = MagicMock()
    adapter.get_server_ip.return_value = "203.0.113.10"

    with patch("app.services.geo_routing_hint.get_adapter_for_node", return_value=adapter), patch(
        "app.services.geo_routing_hint.lookup_ip_geo",
        return_value={"country": "Germany", "city": "Berlin", "geo_label": "Berlin"},
    ), patch(
        "app.services.geo_routing_hint.lookup_ips_geo",
        return_value={
            "203.0.113.10": {"country": "Germany", "city": "Frankfurt", "geo_label": "Frankfurt"},
            "198.51.100.5": {"country": "United States", "city": "New York", "geo_label": "NYC"},
        },
    ):
        hint = build_geo_routing_hint(session, client_ip="203.0.113.55")

    assert hint.recommended_node_name == "eu-1"
    assert "eu-1" in (hint.hint_message or "")
    assert any(node.is_recommended for node in hint.nodes)


def test_geo_routing_hint_api(db_session):
    session, eu, us = db_session
    from app.auth import get_current_user
    from app.database import get_db
    from app.main import app

    user = User(username="admin", password_hash="hash", role=UserRole.admin, theme="dark")

    def override_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user

    adapter = MagicMock()
    adapter.get_server_ip.return_value = "203.0.113.10"
    with patch("app.services.geo_routing_hint.get_adapter_for_node", return_value=adapter), patch(
        "app.services.geo_routing_hint.lookup_ip_geo",
        return_value={"country": "Germany", "city": "Berlin", "geo_label": "Berlin"},
    ), patch(
        "app.services.geo_routing_hint.lookup_ips_geo",
        return_value={"203.0.113.10": {"country": "Germany", "city": "Frankfurt", "geo_label": "Frankfurt"}},
    ):
        client = TestClient(app)
        resp = client.get("/api/nodes/geo-routing-hint?client_ip=203.0.113.55")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommended_node_name"] == "eu-1"
    assert len(body["nodes"]) == 2


def test_policy_summary_api(db_session):
    session, eu, us = db_session
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
    client = TestClient(app)
    resp = client.get("/api/client-access/policy-summary-by-node")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert any(item["node_name"] == "eu-1" and item["blocked_clients"] == 1 for item in body)
