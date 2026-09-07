"""CIDR route count TTL cache for monitoring overview collects."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services import node_compare_metrics as ncm


def test_extract_cidr_routes_count_caches_by_node(monkeypatch):
    ncm.clear_cidr_routes_count_cache()
    adapter = MagicMock()
    adapter.get_routing_overview.return_value = {
        "route_stats": {"result_route_ips_count": 42},
    }

    assert ncm.extract_cidr_routes_count(adapter, node_id=3) == 42
    assert ncm.extract_cidr_routes_count(adapter, node_id=3) == 42
    assert adapter.get_routing_overview.call_count == 1

    adapter.get_routing_overview.return_value = {
        "route_stats": {"result_route_ips_count": 99},
    }
    assert ncm.extract_cidr_routes_count(adapter, node_id=4) == 99
    assert adapter.get_routing_overview.call_count == 2


def test_extract_cidr_routes_count_ttl_zero_skips_cache():
    ncm.clear_cidr_routes_count_cache()
    adapter = MagicMock()
    adapter.get_routing_overview.return_value = {
        "route_stats": {"config_include_total": 7},
    }
    assert ncm.extract_cidr_routes_count(adapter, node_id=1, ttl_seconds=0) == 7
    assert ncm.extract_cidr_routes_count(adapter, node_id=1, ttl_seconds=0) == 7
    assert adapter.get_routing_overview.call_count == 2
