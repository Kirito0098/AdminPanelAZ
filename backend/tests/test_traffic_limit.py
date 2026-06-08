"""Traffic limit period and consumption tests (ported from AdminAntizapret)."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, UserTrafficSample
from app.services.traffic_limit import (
    format_traffic_limit_period_label,
    format_traffic_limit_unblock_at,
    get_client_consumed_traffic_bytes,
    get_traffic_limit_period_bounds,
    get_traffic_limit_period_start,
    parse_traffic_limit_bytes,
    parse_traffic_limit_period_days,
    resolve_traffic_limit_state,
)


class TestTrafficLimitPeriodBounds:
    def test_daily_period_bounds(self):
        now = datetime(2026, 6, 6, 15, 30, tzinfo=timezone.utc)
        start, end = get_traffic_limit_period_bounds(1, now=now)

        assert start == datetime(2026, 6, 6, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 6, 7, 0, 0, tzinfo=timezone.utc)

    def test_weekly_period_bounds_monday(self):
        now = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
        start, end = get_traffic_limit_period_bounds(7, now=now)

        assert start == datetime(2026, 6, 8, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc)

    def test_weekly_period_bounds_sunday(self):
        now = datetime(2026, 6, 14, 23, 59, tzinfo=timezone.utc)
        start, end = get_traffic_limit_period_bounds(7, now=now)

        assert start == datetime(2026, 6, 8, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc)

    def test_monthly_period_bounds(self):
        now = datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc)
        start, end = get_traffic_limit_period_bounds(30, now=now)

        assert start == datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)

    def test_monthly_period_bounds_december(self):
        now = datetime(2026, 12, 31, 23, 0, tzinfo=timezone.utc)
        start, end = get_traffic_limit_period_bounds(30, now=now)

        assert start == datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc)

    def test_period_labels(self):
        assert format_traffic_limit_period_label(1) == "за сутки (календарный день)"
        assert format_traffic_limit_period_label(7) == "за неделю (пн–вс)"
        assert format_traffic_limit_period_label(30) == "за месяц"

    def test_unblock_at_daily(self):
        now = datetime(2026, 6, 6, 15, 30, tzinfo=timezone.utc)
        unblock_at, label = format_traffic_limit_unblock_at(1, now=now)

        assert unblock_at == "2026-06-07 00:00:00"
        assert label == "Авторазблокировка: 07.06.2026 00:00 UTC"

    def test_unblock_at_weekly(self):
        now = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)
        unblock_at, label = format_traffic_limit_unblock_at(7, now=now)

        assert unblock_at == "2026-06-15 00:00:00"
        assert "15.06.2026 00:00 UTC" in label
        assert "(пн)" in label

    def test_unblock_at_monthly(self):
        now = datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc)
        unblock_at, label = format_traffic_limit_unblock_at(30, now=now)

        assert unblock_at == "2026-07-01 00:00:00"
        assert label == "Авторазблокировка: 01.07.2026 00:00 UTC"

    def test_resolve_traffic_limit_state_includes_unblock_label(self):
        state = resolve_traffic_limit_state(
            traffic_limit_bytes=1024,
            traffic_limit_period_days=7,
            consumed_bytes=2048,
        )

        assert state["traffic_limit_exceeded"] is True
        assert state["traffic_limit_unblock_at"] is not None
        assert state["traffic_limit_unblock_label"].startswith("Авторазблокировка:")


class TestTrafficLimitParsing:
    def test_parse_traffic_limit_bytes_mb(self):
        assert parse_traffic_limit_bytes(10, unit="mb") == 10 * 1024 * 1024

    def test_parse_traffic_limit_period_days(self):
        assert parse_traffic_limit_period_days("7") == 7
        assert parse_traffic_limit_period_days(None) is None

    def test_parse_traffic_limit_period_days_invalid(self):
        with pytest.raises(ValueError, match="1, 7 или 30"):
            parse_traffic_limit_period_days("14")


@pytest.fixture()
def traffic_db(tmp_path):
    db_path = tmp_path / "traffic_limit.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    node = Node(
        name="local",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        status=NodeStatus.online,
    )
    session.add(node)
    session.commit()
    yield session, node
    session.close()


def _add_sample(session, *, node_id, common_name, created_at, delta_received=0, delta_sent=0):
    sample = UserTrafficSample(
        node_id=node_id,
        common_name=common_name,
        network_type="vpn",
        protocol_type="openvpn",
        delta_received=delta_received,
        delta_sent=delta_sent,
        created_at=created_at,
    )
    session.add(sample)
    session.commit()


def test_daily_consumption_ignores_previous_day(traffic_db):
    session, node = traffic_db
    _add_sample(
        session,
        node_id=node.id,
        common_name="alice",
        created_at=datetime(2026, 6, 5, 23, 0),
        delta_received=900,
        delta_sent=100,
    )
    _add_sample(
        session,
        node_id=node.id,
        common_name="alice",
        created_at=datetime(2026, 6, 6, 0, 30),
        delta_received=300,
        delta_sent=50,
    )
    fixed_now = datetime(2026, 6, 6, 1, 0, tzinfo=timezone.utc)
    with patch("app.services.traffic_limit.datetime") as dt_mock:
        dt_mock.now.return_value = fixed_now
        dt_mock.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        consumed = get_client_consumed_traffic_bytes(
            session,
            client_name="alice",
            node_id=node.id,
            period_days=1,
        )
    assert consumed == 350


def test_weekly_consumption_ignores_previous_week(traffic_db):
    session, node = traffic_db
    _add_sample(
        session,
        node_id=node.id,
        common_name="bob",
        created_at=datetime(2026, 6, 7, 23, 0),
        delta_received=5000,
    )
    _add_sample(
        session,
        node_id=node.id,
        common_name="bob",
        created_at=datetime(2026, 6, 8, 10, 0),
        delta_received=200,
        delta_sent=50,
    )
    fixed_now = datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)
    with patch("app.services.traffic_limit.datetime") as dt_mock:
        dt_mock.now.return_value = fixed_now
        dt_mock.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        consumed = get_client_consumed_traffic_bytes(
            session,
            client_name="bob",
            node_id=node.id,
            period_days=7,
        )
    assert consumed == 250


def test_monthly_consumption_ignores_previous_month(traffic_db):
    session, node = traffic_db
    _add_sample(
        session,
        node_id=node.id,
        common_name="carol",
        created_at=datetime(2026, 6, 30, 22, 0),
        delta_received=8000,
    )
    _add_sample(
        session,
        node_id=node.id,
        common_name="carol",
        created_at=datetime(2026, 7, 1, 9, 0),
        delta_received=100,
    )
    fixed_now = datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc)
    with patch("app.services.traffic_limit.datetime") as dt_mock:
        dt_mock.now.return_value = fixed_now
        dt_mock.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        consumed = get_client_consumed_traffic_bytes(
            session,
            client_name="carol",
            node_id=node.id,
            period_days=30,
        )
    assert consumed == 100


def test_period_start_midnight_boundary():
    old_period = datetime(2026, 6, 5, 23, 59, tzinfo=timezone.utc)
    new_period = datetime(2026, 6, 6, 0, 0, tzinfo=timezone.utc)

    old_start = get_traffic_limit_period_start(1, now=old_period)
    new_start = get_traffic_limit_period_start(1, now=new_period)

    assert old_start != new_start
    assert new_start == datetime(2026, 6, 6, 0, 0, tzinfo=timezone.utc)
