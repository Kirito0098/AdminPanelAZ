"""Proxy NOC enrichment wired into monitoring overview."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.schemas import OpenVpnClient, WireGuardPeer
from app.services import monitoring_overview as mo
from app.services.proxy_noc_enrich import clear_proxy_mappings_cache


PROXY_IP = "198.51.100.1"
HOME_IP = "203.0.113.10"


@pytest.fixture(autouse=True)
def _clear_proxy_cache():
    clear_proxy_mappings_cache()
    yield
    clear_proxy_mappings_cache()


def _ovpn(real_address: str) -> OpenVpnClient:
    return OpenVpnClient(
        common_name="alice",
        real_address=real_address,
        virtual_address="10.8.0.2",
        bytes_received=1,
        bytes_sent=2,
        connected_since="2026-01-01",
        connected_since_ts=1,
    )


def _wg(endpoint: str | None) -> WireGuardPeer:
    return WireGuardPeer(
        interface="wg0",
        public_key="pk",
        endpoint=endpoint,
        client_name="bob",
    )


def _proxy_node(node_id: int = 9, host: str = PROXY_IP):
    return SimpleNamespace(id=node_id, host=host, name="proxy-1", node_kind="proxy")


def test_load_proxy_noc_context_toggle_off_skips_adapters(monkeypatch):
    monkeypatch.setattr(mo, "is_proxy_nodes_enabled", lambda _db: False)
    get_proxy = MagicMock()
    monkeypatch.setattr(mo, "get_proxy_adapter", get_proxy)
    db = MagicMock()

    proxy_ips, mappings = mo._load_proxy_noc_context(db)

    assert proxy_ips == set()
    assert mappings == {}
    db.query.assert_not_called()
    get_proxy.assert_not_called()


def test_load_proxy_noc_context_fetches_mappings(monkeypatch):
    monkeypatch.setattr(mo, "is_proxy_nodes_enabled", lambda _db: True)
    proxy = _proxy_node()
    query = MagicMock()
    query.filter.return_value.all.return_value = [proxy]
    db = MagicMock()
    db.query.return_value = query

    adapter = MagicMock()
    adapter.mappings.return_value = {
        "mappings": [{"client_ip": HOME_IP, "proxy_sport": 40001}],
    }
    get_proxy = MagicMock(return_value=adapter)
    monkeypatch.setattr(mo, "get_proxy_adapter", get_proxy)

    proxy_ips, mappings = mo._load_proxy_noc_context(db)

    assert proxy_ips == {PROXY_IP}
    assert mappings[PROXY_IP] == [{"client_ip": HOME_IP, "proxy_sport": 40001}]
    get_proxy.assert_called_once_with(proxy)
    # Caller copy must not mutate cache
    mappings[PROXY_IP].append({"client_ip": "9.9.9.9", "proxy_sport": 1})
    again_ips, again_map = mo._load_proxy_noc_context(db)
    assert again_map[PROXY_IP] == [{"client_ip": HOME_IP, "proxy_sport": 40001}]
    assert again_ips == {PROXY_IP}


def test_enrich_resolved_uses_home_ip_for_display_and_geo():
    proxy_ips = {PROXY_IP}
    mappings = {PROXY_IP: [{"client_ip": HOME_IP, "proxy_sport": 40001}]}
    geo_map = {
        HOME_IP: {
            "city": "HomeCity",
            "country": "HC",
            "isp": "HomeISP",
            "location_label": "HomeCity, HC",
            "geo_label": "HomeCity, HC",
        },
        PROXY_IP: {
            "city": "ProxyCity",
            "country": "PC",
            "isp": "ProxyISP",
            "location_label": "ProxyCity, PC",
            "geo_label": "ProxyCity, PC",
        },
    }

    clients = mo.enrich_openvpn_clients(
        [_ovpn(f"{PROXY_IP}:40001")],
        geo_map,
        proxy_ips=proxy_ips,
        mappings_by_proxy_ip=mappings,
    )
    peers = mo.enrich_wireguard_peers(
        [_wg(f"{PROXY_IP}:40001")],
        geo_map,
        proxy_ips=proxy_ips,
        mappings_by_proxy_ip=mappings,
    )

    assert clients[0].via_proxy is True
    assert clients[0].proxy_resolved is True
    assert clients[0].client_ip == HOME_IP
    assert clients[0].display_address == HOME_IP
    assert clients[0].city == "HomeCity"

    assert peers[0].via_proxy is True
    assert peers[0].proxy_resolved is True
    assert peers[0].client_ip == HOME_IP
    assert peers[0].display_address == HOME_IP
    assert peers[0].city == "HomeCity"


def test_enrich_wrong_port_via_unresolved_uses_proxy_geo():
    proxy_ips = {PROXY_IP}
    mappings = {PROXY_IP: [{"client_ip": HOME_IP, "proxy_sport": 40001}]}
    geo_map = {
        PROXY_IP: {
            "city": "ProxyCity",
            "country": "PC",
            "isp": "ProxyISP",
            "location_label": "ProxyCity, PC",
            "geo_label": "ProxyCity, PC",
        },
    }

    clients = mo.enrich_openvpn_clients(
        [_ovpn(f"{PROXY_IP}:40002")],
        geo_map,
        proxy_ips=proxy_ips,
        mappings_by_proxy_ip=mappings,
    )

    assert clients[0].via_proxy is True
    assert clients[0].proxy_resolved is False
    assert clients[0].client_ip == PROXY_IP
    assert clients[0].display_address == f"{PROXY_IP}:40002"
    assert clients[0].city == "ProxyCity"


def test_collect_lookup_ips_prefers_home_when_resolved():
    proxy_ips = {PROXY_IP}
    mappings = {PROXY_IP: [{"client_ip": HOME_IP, "proxy_sport": 40001}]}
    ips = mo._collect_lookup_ips(
        [_ovpn(f"{PROXY_IP}:40001"), _ovpn(f"{PROXY_IP}:40002"), _ovpn("8.8.8.8:1194")],
        [_wg(f"{PROXY_IP}:40001")],
        proxy_ips=proxy_ips,
        mappings_by_proxy_ip=mappings,
    )
    assert ips == [HOME_IP, PROXY_IP, "8.8.8.8", HOME_IP]


def test_match_scoped_per_proxy_ip_avoids_cross_proxy_sport():
    """Same sport on another proxy must not resolve this endpoint."""
    other_proxy = "198.51.100.2"
    proxy_ips = {PROXY_IP, other_proxy}
    mappings = {
        PROXY_IP: [],
        other_proxy: [{"client_ip": HOME_IP, "proxy_sport": 40001}],
    }
    resolved, via, proxy_resolved = mo._match_endpoint_proxy(
        f"{PROXY_IP}:40001", proxy_ips, mappings
    )
    assert via is True
    assert proxy_resolved is False
    assert resolved is None


def test_build_overview_toggle_off_no_proxy_adapter(monkeypatch):
    monkeypatch.setattr(mo, "is_proxy_nodes_enabled", lambda _db: False)
    get_proxy = MagicMock()
    monkeypatch.setattr(mo, "get_proxy_adapter", get_proxy)

    vpn_node = SimpleNamespace(id=1, name="vpn", status=SimpleNamespace(value="online"))
    adapter = MagicMock()
    adapter.get_openvpn_status_snapshot.return_value = ([_ovpn("8.8.8.8:1194")], "status_log")
    adapter.parse_wireguard_status.return_value = []
    adapter.get_service_status.return_value = []
    adapter.get_server_ip.return_value = "1.2.3.4"
    monkeypatch.setattr(mo, "get_adapter_for_node", lambda _n: adapter)

    geo_calls: list = []

    def fake_geo(ips):
        geo_calls.append(list(ips))
        return {}

    monkeypatch.setattr(mo, "lookup_ips_geo", fake_geo)
    monkeypatch.setattr(mo, "resolve_geoip_mode", lambda: "none")

    overview = mo.build_monitoring_overview_for_node(MagicMock(), vpn_node)

    assert len(overview.openvpn_clients) == 1
    assert overview.openvpn_clients[0].via_proxy is False
    get_proxy.assert_not_called()
    assert geo_calls == [["8.8.8.8"]]


def test_build_overview_resolved_and_geo_uses_home(monkeypatch):
    monkeypatch.setattr(mo, "is_proxy_nodes_enabled", lambda _db: True)
    proxy = _proxy_node()
    query = MagicMock()
    query.filter.return_value.all.return_value = [proxy]
    db = MagicMock()
    db.query.return_value = query

    adapter_proxy = MagicMock()
    adapter_proxy.mappings.return_value = {
        "mappings": [{"client_ip": HOME_IP, "proxy_sport": 40001}],
    }
    monkeypatch.setattr(mo, "get_proxy_adapter", MagicMock(return_value=adapter_proxy))

    vpn_node = SimpleNamespace(id=1, name="vpn", status=SimpleNamespace(value="online"))
    adapter = MagicMock()
    adapter.get_openvpn_status_snapshot.return_value = (
        [_ovpn(f"{PROXY_IP}:40001")],
        "status_log",
    )
    adapter.parse_wireguard_status.return_value = []
    adapter.get_service_status.return_value = []
    adapter.get_server_ip.return_value = "1.2.3.4"
    monkeypatch.setattr(mo, "get_adapter_for_node", lambda _n: adapter)

    geo_calls: list = []

    def fake_geo(ips):
        geo_calls.append(list(ips))
        return {
            HOME_IP: {
                "city": "HomeCity",
                "country": "HC",
                "isp": None,
                "location_label": "HomeCity, HC",
                "geo_label": "HomeCity, HC",
            }
        }

    monkeypatch.setattr(mo, "lookup_ips_geo", fake_geo)
    monkeypatch.setattr(mo, "resolve_geoip_mode", lambda: "none")

    overview = mo.build_monitoring_overview_for_node(db, vpn_node)
    client = overview.openvpn_clients[0]

    assert geo_calls == [[HOME_IP]]
    assert client.via_proxy is True
    assert client.proxy_resolved is True
    assert client.client_ip == HOME_IP
    assert client.city == "HomeCity"


def test_build_overview_agent_failure_still_marks_via_proxy(monkeypatch):
    monkeypatch.setattr(mo, "is_proxy_nodes_enabled", lambda _db: True)
    proxy = _proxy_node()
    query = MagicMock()
    query.filter.return_value.all.return_value = [proxy]
    db = MagicMock()
    db.query.return_value = query

    monkeypatch.setattr(
        mo,
        "get_proxy_adapter",
        MagicMock(side_effect=RuntimeError("agent down")),
    )

    vpn_node = SimpleNamespace(id=1, name="vpn", status=SimpleNamespace(value="online"))
    adapter = MagicMock()
    adapter.get_openvpn_status_snapshot.return_value = (
        [_ovpn(f"{PROXY_IP}:40001")],
        "status_log",
    )
    adapter.parse_wireguard_status.return_value = [_wg(f"{PROXY_IP}:40001")]
    adapter.get_service_status.return_value = []
    adapter.get_server_ip.return_value = "1.2.3.4"
    monkeypatch.setattr(mo, "get_adapter_for_node", lambda _n: adapter)
    monkeypatch.setattr(
        mo,
        "lookup_ips_geo",
        lambda ips: {
            PROXY_IP: {
                "city": "ProxyCity",
                "country": "PC",
                "isp": None,
                "location_label": "ProxyCity, PC",
                "geo_label": "ProxyCity, PC",
            }
        },
    )
    monkeypatch.setattr(mo, "resolve_geoip_mode", lambda: "none")

    overview = mo.build_monitoring_overview_for_node(db, vpn_node)

    assert overview.openvpn_clients[0].via_proxy is True
    assert overview.openvpn_clients[0].proxy_resolved is False
    assert overview.openvpn_clients[0].client_ip == PROXY_IP
    assert overview.wireguard_peers[0].via_proxy is True
    assert overview.wireguard_peers[0].proxy_resolved is False
