"""Traffic overview period sums: long windows stream the (node, client, protocol) covering index."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, UserTrafficSample
from app.services.traffic.collector import TrafficCollectorService

CLIENT_INDEX = "ix_user_traffic_sample_node_client_created"
NOW = datetime(2026, 9, 27, 12, 0, 0)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([Node(id=1, name="n1", host="10.0.0.1"), Node(id=2, name="n2", host="10.0.0.2")])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _sample(node_id, name, protocol, received, sent, at):
    return UserTrafficSample(
        node_id=node_id,
        common_name=name,
        network_type="vpn",
        protocol_type=protocol,
        delta_received=received,
        delta_sent=sent,
        created_at=at,
    )


@pytest.fixture()
def samples(db):
    rows = []
    for hours_ago in (1, 5, 30, 24 * 6, 24 * 20, 24 * 29, 24 * 31, 24 * 45):
        at = NOW - timedelta(hours=hours_ago)
        rows += [
            _sample(1, "Alice", "openvpn-udp", 100 + hours_ago, 7, at),
            _sample(1, "alice", "openvpn-udp", 11, 3 * hours_ago, at),
            _sample(1, "alice", "wireguard", 5, 5, at),
            _sample(1, "Bob", "openvpn-tcp", hours_ago, 0, at),
            _sample(2, "ALICE", "openvpn-udp", 1000, hours_ago, at),
            _sample(2, "carol", "amneziawg2", 0, 0, at),
        ]
    rows.append(_sample(1, "Alice", "openvpn-udp", 999, 999, NOW))
    db.add_all(rows)
    db.commit()


def _reference_recent_usage(db, node_ids, since_utc, until_utc):
    delta = func.coalesce(UserTrafficSample.delta_received, 0) + func.coalesce(UserTrafficSample.delta_sent, 0)
    common_name_lower = func.lower(UserTrafficSample.common_name)
    rows = (
        db.query(
            UserTrafficSample.node_id,
            common_name_lower.label("cn"),
            UserTrafficSample.protocol_type,
            func.sum(delta).label("period_bytes"),
        )
        .filter(
            UserTrafficSample.node_id.in_(node_ids),
            UserTrafficSample.created_at >= since_utc,
            UserTrafficSample.created_at < until_utc,
        )
        .group_by(UserTrafficSample.node_id, common_name_lower, UserTrafficSample.protocol_type)
        .all()
    )
    return {(r.node_id, r.cn or "", r.protocol_type): {"period": int(r.period_bytes or 0)} for r in rows}


@pytest.mark.parametrize("days", [1, 3, 7, 30, 90])
@pytest.mark.parametrize("node_ids", [[1], [1, 2]])
def test_recent_usage_matches_reference(db, samples, days, node_ids):
    since = NOW - timedelta(days=days)
    svc = TrafficCollectorService(db, node_ids[0])

    got = svc._recent_usage(node_ids, since_utc=since, until_utc=NOW, ttl_seconds=None)

    assert got == _reference_recent_usage(db, node_ids, since, NOW)
    assert got


def _captured_plan(db, since):
    engine = db.get_bind()
    captured: list[tuple[str, object]] = []

    def _capture(_conn, _cursor, statement, params, _context, _executemany):
        if "user_traffic_sample" in statement and "sum(" in statement.lower():
            captured.append((statement, params))

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        TrafficCollectorService(db, 1)._recent_usage([1, 2], since_utc=since, until_utc=NOW, ttl_seconds=None)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert len(captured) == 1
    statement, params = captured[0]
    with engine.connect() as conn:
        return " | ".join(str(row) for row in conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {statement}", params))


def test_long_window_streams_covering_client_index(db, samples):
    plan = _captured_plan(db, NOW - timedelta(days=30))

    assert f"COVERING INDEX {CLIENT_INDEX}" in plan, plan
    assert "TEMP B-TREE" not in plan, plan


def test_short_window_keeps_created_at_range(db, samples):
    plan = _captured_plan(db, NOW - timedelta(days=1))

    assert "ix_user_traffic_sample_node_created" in plan, plan


def test_migration_adds_client_index_idempotently(db, monkeypatch):
    from app import database

    engine = db.get_bind()
    with engine.begin() as conn:
        conn.execute(text(f"DROP INDEX {CLIENT_INDEX}"))
    monkeypatch.setattr(database, "engine", engine)

    database._migrate_user_traffic_sample_node_client_index()
    database._migrate_user_traffic_sample_node_client_index()

    names = {idx["name"] for idx in inspect(engine).get_indexes("user_traffic_sample")}
    assert CLIENT_INDEX in names
