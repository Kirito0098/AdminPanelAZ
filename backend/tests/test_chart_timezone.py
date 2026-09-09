from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import UserTrafficSample
import app.services.traffic.chart as traffic_chart_module
from app.services.chart_timezone import (
    local_bucket_start_as_utc_iso,
    naive_utc_to_local,
    resolve_chart_timezone,
)
from app.services.traffic.chart import fetch_traffic_chart


def test_resolve_prefers_explicit_then_falls_back_utc():
    assert resolve_chart_timezone(explicit="Europe/Moscow") == "Europe/Moscow"
    assert resolve_chart_timezone(explicit="Not/AZone") == "UTC"
    assert resolve_chart_timezone() == "UTC"


def test_naive_utc_to_moscow():
    local = naive_utc_to_local(datetime(2026, 9, 7, 8, 56, 0), "Europe/Moscow")
    assert local.hour == 11
    assert local.tzinfo is not None


def test_hour_bucket_start_iso_moscow():
    local = naive_utc_to_local(datetime(2026, 9, 7, 8, 56, 0), "Europe/Moscow")
    iso = local_bucket_start_as_utc_iso(local, "hour")
    # Local 11:00 MSK == 08:00 UTC
    assert iso.startswith("2026-09-07T08:00:00")


@pytest.fixture()
def chart_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_traffic_chart_hour_bucket_uses_moscow(chart_db, monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return datetime(2026, 9, 8, 8, 56, 0)

    monkeypatch.setattr(traffic_chart_module, "datetime", FixedDateTime)
    chart_db.add(
        UserTrafficSample(
            node_id=1,
            common_name="ivan",
            network_type="vpn",
            protocol_type="openvpn",
            delta_received=100,
            delta_sent=0,
            created_at=datetime(2026, 9, 7, 8, 56, 0),
        )
    )
    chart_db.commit()

    result = fetch_traffic_chart(
        chart_db,
        1,
        "ivan",
        "1d",
        "all",
        tz_name="Europe/Moscow",
    )

    assert result["timezone"] == "Europe/Moscow"
    assert result["bucket"] == "hour"
    assert len(result["timestamps"]) == 1
    assert result["timestamps"][0].startswith("2026-09-07T08:00:00")
    assert result["labels"]
