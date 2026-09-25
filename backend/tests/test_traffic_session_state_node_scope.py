"""Traffic session state must be unique per node, not globally (HA replicas share WG peers)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Base, migrate_traffic_session_state_node_scoped_key
from app.models import Node, TrafficSessionState
from app.services.traffic import worker as worker_mod
from app.services.traffic.collector import TrafficCollectorService


def _wg_status_rows(rx: int = 100, tx: int = 200) -> list[dict]:
    return [
        {
            "profile": "antizapret-wg",
            "traffic_clients": [
                {
                    "session_kind": "wireguard",
                    "common_name": "alice",
                    "peer_public_key": "pk-alice",
                    "virtual_address": "10.29.8.2",
                    "bytes_received": rx,
                    "bytes_sent": tx,
                }
            ],
        }
    ]


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all(
        [
            Node(id=1, name="primary", host="127.0.0.1", is_local=True),
            Node(id=2, name="replica", host="10.0.0.2", is_local=False),
        ]
    )
    db.commit()
    db.close()
    try:
        yield factory
    finally:
        engine.dispose()


def test_same_wireguard_peer_on_two_nodes_is_tracked_separately(session_factory):
    db = session_factory()
    try:
        TrafficCollectorService(db, 1).persist_snapshot(_wg_status_rows())
        TrafficCollectorService(db, 2).persist_snapshot(_wg_status_rows())

        rows = db.query(TrafficSessionState).order_by(TrafficSessionState.node_id).all()
        assert [row.node_id for row in rows] == [1, 2]
        assert rows[0].session_key == rows[1].session_key
    finally:
        db.close()


def test_collector_recovers_after_db_error_on_one_node(session_factory, monkeypatch):
    nodes_seen: list[int] = []
    real_persist = TrafficCollectorService.persist_snapshot

    def _persist(self, status_rows):
        nodes_seen.append(self.node_id)
        if self.node_id == 1:
            self.db.add(TrafficSessionState(node_id=1, session_key=None, common_name="broken"))
            self.db.flush()
        return real_persist(self, status_rows)

    adapter = MagicMock()
    adapter.parse_openvpn_status.return_value = []
    adapter.parse_wireguard_status.return_value = []
    monkeypatch.setattr(worker_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(worker_mod, "_is_vpn_node", lambda node: True)
    monkeypatch.setattr(worker_mod, "get_adapter_for_node", lambda node: adapter)
    monkeypatch.setattr(worker_mod, "is_awg2_enabled", lambda db: False)
    monkeypatch.setattr(worker_mod, "build_status_rows", lambda ovpn, wg, awg2: _wg_status_rows())
    monkeypatch.setattr(
        worker_mod,
        "get_settings",
        lambda: SimpleNamespace(traffic_limit_reconcile_after_sync=False),
    )
    monkeypatch.setattr(TrafficCollectorService, "persist_snapshot", _persist)

    worker_mod._collect_all_nodes()

    assert nodes_seen == [1, 2]
    db = session_factory()
    try:
        rows = db.query(TrafficSessionState).all()
        assert [(row.node_id, row.common_name) for row in rows] == [(2, "alice")]
    finally:
        db.close()


def _legacy_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE traffic_session_state ("
                "id INTEGER NOT NULL PRIMARY KEY, node_id INTEGER NOT NULL, "
                "session_key VARCHAR(512) NOT NULL, profile VARCHAR(64) NOT NULL DEFAULT 'unknown', "
                "common_name VARCHAR(128) NOT NULL, real_address VARCHAR(64), virtual_address VARCHAR(64), "
                "connected_since_ts INTEGER NOT NULL DEFAULT 0, last_bytes_received INTEGER NOT NULL DEFAULT 0, "
                "last_bytes_sent INTEGER NOT NULL DEFAULT 0, is_active BOOLEAN NOT NULL DEFAULT 1, "
                "last_seen_at DATETIME, ended_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX ix_traffic_session_state_session_key "
                "ON traffic_session_state (session_key)"
            )
        )
        conn.execute(
            text("INSERT INTO traffic_session_state (node_id, session_key, common_name) VALUES (1, 'k', 'alice')")
        )
    return engine


def _insert(conn, node_id: int, key: str = "k") -> None:
    conn.execute(
        text("INSERT INTO traffic_session_state (node_id, session_key, common_name) VALUES (:n, :k, 'alice')"),
        {"n": node_id, "k": key},
    )


def test_migration_makes_session_key_unique_per_node():
    engine = _legacy_engine()
    try:
        with engine.begin() as conn:
            assert migrate_traffic_session_state_node_scoped_key(conn) is True

        with engine.begin() as conn:
            _insert(conn, node_id=2)
        with pytest.raises(IntegrityError), engine.begin() as conn:
            _insert(conn, node_id=2)

        indexes = {idx["name"]: idx for idx in inspect(engine).get_indexes("traffic_session_state")}
        assert not indexes["ix_traffic_session_state_session_key"]["unique"]
        assert indexes["uq_traffic_session_state_node_session"]["unique"]
    finally:
        engine.dispose()


def test_migration_is_idempotent():
    engine = _legacy_engine()
    try:
        with engine.begin() as conn:
            assert migrate_traffic_session_state_node_scoped_key(conn) is True
        with engine.begin() as conn:
            assert migrate_traffic_session_state_node_scoped_key(conn) is False
    finally:
        engine.dispose()
