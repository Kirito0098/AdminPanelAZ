"""Geo routing hint takes node server IPs from the health-synced node metadata, not a live agent call."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models import NodeStatus
from app.services import geo_routing_hint as geo_hint


def _node(node_id: int, name: str, *, status=NodeStatus.online, metadata: dict | None = None):
    return SimpleNamespace(
        id=node_id,
        name=name,
        node_kind="vpn",
        status=status,
        node_metadata=json.dumps(metadata) if metadata is not None else None,
    )


@pytest.fixture
def geo(monkeypatch):
    looked_up: list[list[str | None]] = []

    def fake_lookup_ips(ips):
        looked_up.append(list(ips))
        return {"198.51.100.7": {"country": "Germany", "city": "Frankfurt", "geo_label": "Frankfurt"}}

    monkeypatch.setattr(geo_hint, "lookup_ip_geo", lambda _ip: {"country": "Germany"})
    monkeypatch.setattr(geo_hint, "lookup_ips_geo", fake_lookup_ips)
    return looked_up


def _db(nodes):
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = nodes
    return db


def test_online_node_uses_health_metadata_server_ip(monkeypatch, geo):
    get_adapter = MagicMock(side_effect=AssertionError("live agent call"))
    monkeypatch.setattr(geo_hint, "get_adapter_for_node", get_adapter)

    hint = geo_hint.build_geo_routing_hint(
        _db([_node(2, "remote", metadata={"server_ip": "198.51.100.7"})]),
        client_ip="203.0.113.9",
    )

    get_adapter.assert_not_called()
    assert geo == [["198.51.100.7"]]
    assert hint.nodes[0].server_ip == "198.51.100.7"
    assert hint.nodes[0].country == "Germany"
    assert hint.recommended_node_id == 2


def test_online_node_without_metadata_ip_falls_back_to_adapter(monkeypatch, geo):
    adapter = MagicMock()
    adapter.get_server_ip.return_value = "198.51.100.7"
    monkeypatch.setattr(geo_hint, "get_adapter_for_node", lambda _node: adapter)

    hint = geo_hint.build_geo_routing_hint(
        _db([_node(1, "local", metadata={"hostname": "vpn"})]),
        client_ip="203.0.113.9",
    )

    adapter.get_server_ip.assert_called_once_with()
    assert hint.nodes[0].server_ip == "198.51.100.7"


def test_offline_node_has_no_server_ip(monkeypatch, geo):
    get_adapter = MagicMock(side_effect=AssertionError("live agent call"))
    monkeypatch.setattr(geo_hint, "get_adapter_for_node", get_adapter)

    hint = geo_hint.build_geo_routing_hint(
        _db([_node(3, "down", status=NodeStatus.offline, metadata={"server_ip": "198.51.100.7"})]),
        client_ip="203.0.113.9",
    )

    get_adapter.assert_not_called()
    assert hint.nodes[0].server_ip is None
