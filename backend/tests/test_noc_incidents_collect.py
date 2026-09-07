"""NOC incidents should probe nodes once (not summary + overview)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import noc_incidents as ni


def test_build_noc_incidents_single_collect(monkeypatch):
    collect_calls = {"n": 0}
    node = SimpleNamespace(id=1, name="vpn-1", status=SimpleNamespace(value="online"))
    inactive = SimpleNamespace(name="openvpn-server", active=False, status="inactive")
    payload = {
        "node": node,
        "ovpn_clients": [],
        "wireguard_peers": [],
        "amneziawg2_peers": [],
        "services": [inactive],
        "error": None,
        "cpu_percent": 10.0,
        "memory_percent": 20.0,
        "total_traffic_bytes": 0,
        "cidr_routes_count": None,
    }
    summary = SimpleNamespace(
        node_id=1,
        error=None,
        health_score=90,
        health_level="ok",
    )

    def fake_collect(_db):
        collect_calls["n"] += 1
        return [payload]

    monkeypatch.setattr(ni, "_collect_nodes_monitoring_data", fake_collect)
    monkeypatch.setattr(ni, "_build_node_summary", lambda _payload: summary)
    monkeypatch.setattr(ni, "get_active_node", lambda _db: node)
    monkeypatch.setattr(ni, "_is_vpn_node", lambda _n: True)

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    # Node list query
    node_q = MagicMock()
    node_q.order_by.return_value.all.return_value = [node]
    cidr_q = MagicMock()
    cidr_q.filter.return_value.order_by.return_value.all.return_value = []

    def query_side_effect(model):
        name = getattr(model, "__name__", str(model))
        if "AlertRule" in name:
            q = MagicMock()
            q.filter.return_value.order_by.return_value.all.return_value = []
            return q
        if "CidrDbRefreshLog" in name:
            return cidr_q
        return node_q

    db.query.side_effect = query_side_effect

    resp = ni.build_noc_incidents(db, limit=20)
    assert collect_calls["n"] == 1
    kinds = {item.kind for item in resp.items}
    assert "service_down" in kinds
    assert any(item.id == "service_down:1:openvpn-server" for item in resp.items)
