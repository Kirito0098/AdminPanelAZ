from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas import WireGuardPeer
from app.services import connection_history as ch


def test_aggregate_bucket_includes_amneziawg2():
    sample = SimpleNamespace(
        created_at=datetime.utcnow(),
        node_id=1,
        openvpn_count=1,
        wireguard_count=2,
        amneziawg2_count=3,
    )
    point = ch._aggregate_bucket([sample], sum_nodes=False)
    assert point["amneziawg2"] == 3
    assert point["total"] == 6


def test_collect_samples_awg2_when_enabled(monkeypatch):
    monkeypatch.setattr(ch, "is_awg2_enabled", lambda _db: True)
    node = SimpleNamespace(id=1, name="n", status="online")
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = [node]
    adapter = MagicMock()
    monkeypatch.setattr(ch, "get_adapter_for_node", lambda _n: adapter)
    persisted = {}

    def fake_persist(db, node_id, *, openvpn_count, wireguard_count, amneziawg2_count=0):
        persisted.update(
            openvpn_count=openvpn_count,
            wireguard_count=wireguard_count,
            amneziawg2_count=amneziawg2_count,
        )
        return MagicMock()

    monkeypatch.setattr(ch, "persist_connection_sample", fake_persist)
    monkeypatch.setattr(adapter, "get_openvpn_status_snapshot", lambda: ([], "status_log"))
    monkeypatch.setattr(adapter, "parse_wireguard_status", lambda: [])
    now = datetime.utcnow()
    online = WireGuardPeer(
        interface="a",
        public_key="p",
        client_name="c",
        latest_handshake=(now - timedelta(seconds=5)).isoformat(),
    )
    monkeypatch.setattr(ch, "fetch_awg2_peers_for_adapter", lambda _a: [online])
    ch.collect_connection_samples(db)
    assert persisted["amneziawg2_count"] == 1


def test_collect_samples_awg2_zero_when_toggle_off(monkeypatch):
    monkeypatch.setattr(ch, "is_awg2_enabled", lambda _db: False)
    fetch = MagicMock()
    monkeypatch.setattr(ch, "fetch_awg2_peers_for_adapter", fetch)
    node = SimpleNamespace(id=1, name="n", status="online")
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = [node]
    adapter = MagicMock()
    adapter.get_openvpn_status_snapshot.return_value = ([], "status_log")
    adapter.parse_wireguard_status.return_value = []
    monkeypatch.setattr(ch, "get_adapter_for_node", lambda _n: adapter)
    monkeypatch.setattr(ch, "persist_connection_sample", MagicMock())
    ch.collect_connection_samples(db)
    fetch.assert_not_called()
