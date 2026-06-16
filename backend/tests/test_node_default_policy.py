"""Tests for per-node default access policies (EU vs RU wizard backend)."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, OpenVpnAccessPolicy, WgAccessPolicy
from app.services.access_policy import (
    NODE_DEFAULT_POLICY_CLIENT,
    build_policy_summary_by_node,
    get_node_default_policy,
    is_node_default_policy_client,
    set_node_default_policy,
)


@pytest.fixture()
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    eu = Node(name="eu-1", host="10.0.0.1", port=9100, is_local=True, status=NodeStatus.online)
    ru = Node(name="ru-1", host="10.0.0.2", port=9100, is_local=False, status=NodeStatus.online)
    session.add_all([eu, ru])
    session.commit()
    session.refresh(eu)
    session.refresh(ru)
    yield session, eu, ru
    session.close()


def test_is_node_default_policy_client():
    assert is_node_default_policy_client(NODE_DEFAULT_POLICY_CLIENT)
    assert is_node_default_policy_client("__NODE_DEFAULT__")
    assert not is_node_default_policy_client("alice")


def test_set_and_get_node_default_policy_eu_vs_ru(db_session):
    session, eu, ru = db_session

    set_node_default_policy(
        session,
        eu.id,
        route_mode="route_selective",
        openvpn_limit_value=100,
        openvpn_limit_unit="GB",
        wireguard_limit_value=50,
        wireguard_limit_unit="GB",
        wireguard_limit_period_days=30,
        actor="admin",
    )
    set_node_default_policy(
        session,
        ru.id,
        route_mode="route_all",
        openvpn_limit_value=200,
        openvpn_limit_unit="GB",
        openvpn_limit_period_days=7,
        wireguard_limit_value=80,
        wireguard_limit_unit="GB",
        actor="admin",
    )

    eu_defaults = get_node_default_policy(session, eu.id)
    ru_defaults = get_node_default_policy(session, ru.id)

    assert eu_defaults["route_mode"] == "route_selective"
    assert eu_defaults["openvpn"]["limit_human"] == "100.0 GB"
    assert eu_defaults["wireguard"]["limit_period_days"] == 30

    assert ru_defaults["route_mode"] == "route_all"
    assert ru_defaults["openvpn"]["limit_period_days"] == 7
    assert ru_defaults["wireguard"]["limit_human"] == "80.0 GB"


def test_build_policy_summary_excludes_default_rows(db_session):
    session, eu, ru = db_session

    set_node_default_policy(
        session,
        eu.id,
        openvpn_limit_value=10,
        openvpn_limit_unit="GB",
        actor="admin",
    )
    session.add(
        OpenVpnAccessPolicy(
            node_id=eu.id,
            client_name="alice",
            is_permanent_blocked=True,
        )
    )
    session.add(
        WgAccessPolicy(
            node_id=ru.id,
            client_name="bob",
            traffic_limit_bytes=5_000_000,
        )
    )
    session.commit()

    summaries = build_policy_summary_by_node(session)
    by_name = {item["node_name"]: item for item in summaries}

    assert by_name["eu-1"]["openvpn_policies"] == 1
    assert by_name["eu-1"]["blocked_clients"] == 1
    assert by_name["eu-1"]["default_openvpn_limit_human"] == "10.0 GB"
    assert by_name["ru-1"]["wireguard_policies"] == 1
    assert by_name["ru-1"]["traffic_limited_clients"] == 1
    assert by_name["ru-1"]["default_openvpn_limit_human"] is None


def test_reconcile_wg_skips_default_row(db_session):
    session, eu, _ru = db_session
    set_node_default_policy(
        session,
        eu.id,
        wireguard_limit_value=25,
        wireguard_limit_unit="GB",
        actor="admin",
    )

    from app.services.access_policy import AccessPolicyService

    adapter = MagicMock()
    svc = AccessPolicyService(session, antizapret_path=MagicMock(), node_id=eu.id, adapter=adapter)
    with patch("app.services.access_policy.block_client_runtime") as block_runtime, patch(
        "app.services.access_policy.unblock_client_runtime"
    ) as unblock_runtime:
        result = svc.reconcile_all_wg_policies(apply_runtime=True, node_id=eu.id)

    assert result["wg_policy_reconcile"] == "ok"
    assert NODE_DEFAULT_POLICY_CLIENT not in (result.get("blocked_clients") or [])
    assert NODE_DEFAULT_POLICY_CLIENT not in (result.get("unblocked_clients") or [])
    block_runtime.assert_not_called()
    unblock_runtime.assert_not_called()


def test_node_default_policy_api(api_test_env):
    from fastapi.testclient import TestClient

    session = api_test_env["session_factory"]()
    eu = Node(name="eu-1", host="10.0.0.1", port=9100, is_local=False, status=NodeStatus.online)
    ru = Node(name="ru-1", host="10.0.0.2", port=9100, is_local=False, status=NodeStatus.online)
    session.add_all([eu, ru])
    session.commit()
    session.refresh(eu)
    session.refresh(ru)

    client = TestClient(api_test_env["app"])
    headers = api_test_env["admin_headers"]

    with patch("app.main.ip_restriction_service.should_hard_deny", return_value=False), patch(
        "app.main.ip_restriction_service.get_settings",
        return_value={"ip_restriction_enabled": False},
    ), patch("app.main.ip_restriction_service.is_ip_allowed", return_value=True):
        put_resp = client.put(
            f"/api/client-access/node-defaults/{eu.id}",
            headers=headers,
            json={
                "route_mode": "route_selective",
                "openvpn_limit_value": 100,
                "openvpn_limit_unit": "GB",
                "wireguard_limit_value": 50,
                "wireguard_limit_unit": "GB",
                "wireguard_limit_period_days": 30,
            },
        )
        assert put_resp.status_code == 200
        eu_body = put_resp.json()
        assert eu_body["node_name"] == "eu-1"
        assert eu_body["route_mode"] == "route_selective"
        assert eu_body["openvpn"]["limit_human"] == "100.0 GB"

        client.put(
            f"/api/client-access/node-defaults/{ru.id}",
            headers=headers,
            json={
                "route_mode": "route_all",
                "openvpn_limit_value": 200,
                "openvpn_limit_unit": "GB",
            },
        )

        summary_resp = client.get("/api/client-access/policy-summary-by-node", headers=headers)

    session.close()

    assert summary_resp.status_code == 200
    summary = {row["node_name"]: row for row in summary_resp.json()}
    assert summary["eu-1"]["default_openvpn_limit_human"] == "100.0 GB"
    assert summary["eu-1"]["default_route_mode"] == "route_selective"
    assert summary["ru-1"]["default_openvpn_limit_human"] == "200.0 GB"
    assert summary["ru-1"]["default_route_mode"] == "route_all"
