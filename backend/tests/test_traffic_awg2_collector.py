from datetime import datetime, timedelta

from app.schemas import WireGuardPeer
from app.services.traffic.collector import build_status_rows, protocol_type_from_profile


def test_protocol_type_awg2_not_wireguard():
    assert protocol_type_from_profile("antizapret-awg2") == "amneziawg2"
    assert protocol_type_from_profile("vpn-awg2") == "amneziawg2"
    assert protocol_type_from_profile("antizapret-awg") == "wireguard"  # stock path unchanged
    assert protocol_type_from_profile("antizapret-wg") == "wireguard"


def test_build_status_rows_includes_online_awg2_only():
    now = datetime.utcnow()
    online = WireGuardPeer(
        interface="antizapret-awg",
        public_key="pk1",
        client_name="ivan",
        endpoint="1.2.3.4:1",
        transfer_rx=10,
        transfer_tx=20,
        latest_handshake=(now - timedelta(seconds=5)).isoformat(),
    )
    offline = WireGuardPeer(
        interface="vpn-awg",
        public_key="pk2",
        client_name="ghost",
        latest_handshake=(now - timedelta(seconds=400)).isoformat(),
    )
    rows = build_status_rows([], [], [online, offline])
    assert len(rows) == 1
    assert rows[0]["profile"] == "antizapret-awg2"
    client = rows[0]["traffic_clients"][0]
    assert client["session_kind"] == "amneziawg2"
    assert client["common_name"] == "ivan"
    assert protocol_type_from_profile(rows[0]["profile"]) == "amneziawg2"


def test_collect_traffic_snapshot_includes_awg2_when_enabled(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.traffic import collector as collector_mod

    now = datetime.utcnow()
    awg2_peer = WireGuardPeer(
        interface="antizapret-awg",
        public_key="pk1",
        client_name="ivan",
        transfer_rx=1,
        transfer_tx=2,
        latest_handshake=(now - timedelta(seconds=5)).isoformat(),
    )

    class _Adapter:
        def parse_openvpn_status(self):
            return []

        def parse_wireguard_status(self):
            return []

    captured: dict = {}

    class _Collector:
        def __init__(self, db, node_id):
            captured["node_id"] = node_id

        def persist_snapshot(self, status_rows):
            captured["rows"] = status_rows
            return {"samples_added": 1, "active_sessions": 1}

    monkeypatch.setattr(
        collector_mod,
        "Node",
        SimpleNamespace,  # unused; db.get patched below
    )
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=5, name="n", node_kind="vpn")
    monkeypatch.setattr(
        "app.services.node_manager._is_vpn_node",
        lambda _n: True,
    )
    monkeypatch.setattr(
        "app.services.node_manager.get_adapter_for_node",
        lambda _n: _Adapter(),
    )
    monkeypatch.setattr(
        "app.services.feature_toggles.is_awg2_enabled",
        lambda _db: True,
    )
    monkeypatch.setattr(
        "app.services.awg2_noc.fetch_awg2_peers_for_adapter",
        lambda _adapter: [awg2_peer],
    )
    monkeypatch.setattr(collector_mod, "TrafficCollectorService", _Collector)

    result = collector_mod.collect_traffic_snapshot_for_node(db, 5)
    assert result["skipped"] is False
    assert len(captured["rows"]) == 1
    assert captured["rows"][0]["profile"] == "antizapret-awg2"


def test_collect_traffic_snapshot_skips_awg2_when_disabled(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.traffic import collector as collector_mod

    class _Adapter:
        def parse_openvpn_status(self):
            return []

        def parse_wireguard_status(self):
            return []

    captured: dict = {}

    class _Collector:
        def __init__(self, db, node_id):
            pass

        def persist_snapshot(self, status_rows):
            captured["rows"] = status_rows
            return {"samples_added": 0, "active_sessions": 0}

    fetch = MagicMock(side_effect=AssertionError("awg2 fetch must not run"))
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=5, name="n", node_kind="vpn")
    monkeypatch.setattr("app.services.node_manager._is_vpn_node", lambda _n: True)
    monkeypatch.setattr("app.services.node_manager.get_adapter_for_node", lambda _n: _Adapter())
    monkeypatch.setattr("app.services.feature_toggles.is_awg2_enabled", lambda _db: False)
    monkeypatch.setattr("app.services.awg2_noc.fetch_awg2_peers_for_adapter", fetch)
    monkeypatch.setattr(collector_mod, "TrafficCollectorService", _Collector)

    result = collector_mod.collect_traffic_snapshot_for_node(db, 5)
    assert result["skipped"] is False
    assert captured["rows"] == []
    fetch.assert_not_called()
