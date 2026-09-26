"""Traffic limit usage: one indexed aggregate per check instead of scanning samples."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, UserTrafficSample, UserTrafficStatProtocol
from app.services.traffic_limit import get_client_consumed_traffic_bytes, get_traffic_limit_period_bounds

UDP = "openvpn-udp"
TCP = "openvpn-tcp"


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


def _stat(node_id: int, name: str, protocol: str, total: int) -> UserTrafficStatProtocol:
    return UserTrafficStatProtocol(
        node_id=node_id,
        common_name=name,
        protocol_type=protocol,
        total_received=total,
        total_sent=0,
        total_received_vpn=0,
        total_sent_vpn=0,
        total_received_antizapret=0,
        total_sent_antizapret=0,
        total_sessions=0,
        updated_at=datetime.utcnow(),
    )


def _sample(node_id: int, name: str, protocol: str, received: int, sent: int, at: datetime) -> UserTrafficSample:
    return UserTrafficSample(
        node_id=node_id,
        common_name=name,
        protocol_type=protocol,
        delta_received=received,
        delta_sent=sent,
        created_at=at,
    )


@pytest.fixture()
def traffic(db):
    month_start, month_end = get_traffic_limit_period_bounds(30, now=datetime.now(timezone.utc))
    in_period = month_start.replace(tzinfo=None) + timedelta(minutes=1)
    before_period = month_start.replace(tzinfo=None) - timedelta(days=1)
    after_period = month_end.replace(tzinfo=None)
    db.add_all(
        [
            _stat(1, "Alice", UDP, 1110),
            _stat(1, "alice", TCP, 10),
            _stat(2, "alice", UDP, 7),
            _stat(1, "bob", UDP, 50),
            _sample(1, "Alice", UDP, 100, 10, in_period),
            _sample(1, "alice", TCP, 5, 5, in_period),
            _sample(1, "Alice", UDP, 1000, 0, before_period),
            _sample(1, "Alice", UDP, 3000, 0, after_period),
            _sample(2, "alice", UDP, 7, 0, in_period),
            _sample(1, "bob", UDP, 50, 0, in_period),
        ]
    )
    db.commit()
    return db


def test_period_usage_sums_all_spellings_within_period(traffic):
    assert get_client_consumed_traffic_bytes(
        traffic, client_name="ALICE", node_id=1, period_days=30, protocol_types={UDP, TCP}
    ) == 120
    assert get_client_consumed_traffic_bytes(
        traffic, client_name="alice", node_id=1, period_days=30, protocol_types={UDP}
    ) == 110
    assert get_client_consumed_traffic_bytes(traffic, client_name="alice", period_days=30) == 127
    assert get_client_consumed_traffic_bytes(traffic, client_name="carol", node_id=1, period_days=30) == 0


def test_all_time_usage_comes_from_totals(traffic):
    assert get_client_consumed_traffic_bytes(
        traffic, client_name="alice", node_id=1, protocol_types={UDP, TCP}
    ) == 1120
    assert get_client_consumed_traffic_bytes(traffic, client_name="alice") == 1127


def test_period_check_is_one_indexed_aggregate(traffic):
    engine = traffic.get_bind()
    captured: list[tuple[str, tuple]] = []

    def _capture(_conn, _cursor, statement, params, _context, _many):
        if "user_traffic_sample" in statement:
            captured.append((statement, params))

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        get_client_consumed_traffic_bytes(
            traffic, client_name="alice", node_id=1, period_days=30, protocol_types={UDP, TCP}
        )
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert len(captured) == 1, [s for s, _ in captured]
    statement, params = captured[0]
    assert "sum(" in statement.lower()
    with engine.connect() as conn:
        plan = conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {statement}", params).fetchall()
    assert any("ix_user_traffic_sample_name_created" in str(row) for row in plan), plan


def test_migration_replaces_single_column_name_index(db, monkeypatch):
    from app import database

    engine = db.get_bind()
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_user_traffic_sample_name_created"))
        conn.execute(text("CREATE INDEX ix_user_traffic_sample_common_name ON user_traffic_sample (common_name)"))
    monkeypatch.setattr(database, "engine", engine)

    database._migrate_user_traffic_sample_name_index()
    database._migrate_user_traffic_sample_name_index()

    names = {idx["name"] for idx in inspect(engine).get_indexes("user_traffic_sample")}
    assert "ix_user_traffic_sample_name_created" in names
    assert "ix_user_traffic_sample_common_name" not in names
