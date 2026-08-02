"""Unit tests for proxy NOC mapping match and cache helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.proxy_noc_enrich import (
    PROXY_MAPPINGS_CACHE_TTL_SEC,
    clear_proxy_mappings_cache,
    get_mappings_for_proxy,
    match_client_ip,
    normalize_proxy_host,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_proxy_mappings_cache()
    yield
    clear_proxy_mappings_cache()


def test_match_resolves_by_sport():
    mappings = [{"client_ip": "203.0.113.10", "client_port": 50000, "proxy_sport": 40001}]
    ip, via, resolved = match_client_ip("198.51.100.1:40001", mappings, {"198.51.100.1"})
    assert via and resolved and ip == "203.0.113.10"


def test_match_wrong_port_via_unresolved():
    mappings = [{"client_ip": "203.0.113.10", "proxy_sport": 40001}]
    ip, via, resolved = match_client_ip("198.51.100.1:40002", mappings, {"198.51.100.1"})
    assert via and not resolved and ip is None


def test_non_proxy_ip():
    ip, via, resolved = match_client_ip("8.8.8.8:1194", [], {"198.51.100.1"})
    assert not via and not resolved and ip is None


def test_normalize_proxy_host_ipv4():
    assert normalize_proxy_host(" 198.51.100.1 ") == "198.51.100.1"
    assert normalize_proxy_host("proxy.example.com") is None
    assert normalize_proxy_host("2001:db8::1") is None
    assert normalize_proxy_host("") is None


def test_get_mappings_cache_ttl_skips_second_fetch():
    assert PROXY_MAPPINGS_CACHE_TTL_SEC == 45
    adapter = MagicMock()
    adapter.mappings.return_value = {
        "mappings": [{"client_ip": "203.0.113.10", "proxy_sport": 40001}],
    }
    factory = MagicMock(return_value=adapter)

    first = get_mappings_for_proxy(factory, 7, now=1000.0)
    second = get_mappings_for_proxy(factory, 7, now=1040.0)
    assert first == second
    assert len(first) == 1
    factory.assert_called_once_with(7)
    adapter.mappings.assert_called_once()


def test_get_mappings_cache_expires():
    adapter = MagicMock()
    adapter.mappings.return_value = {"mappings": [{"client_ip": "10.0.0.1", "proxy_sport": 1}]}
    factory = MagicMock(return_value=adapter)

    get_mappings_for_proxy(factory, 3, now=1000.0)
    get_mappings_for_proxy(factory, 3, now=1000.0 + PROXY_MAPPINGS_CACHE_TTL_SEC + 0.1)
    assert factory.call_count == 2
    assert adapter.mappings.call_count == 2


def test_get_mappings_agent_failure_returns_empty():
    factory = MagicMock(side_effect=RuntimeError("agent down"))
    result = get_mappings_for_proxy(factory, 9, now=1.0)
    assert result == []

    # Failed result is cached — second call within TTL does not re-raise / re-fetch
    factory2 = MagicMock(return_value=SimpleNamespace(mappings=MagicMock()))
    again = get_mappings_for_proxy(factory2, 9, now=10.0)
    assert again == []
    factory2.assert_not_called()
