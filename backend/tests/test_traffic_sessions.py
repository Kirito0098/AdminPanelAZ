"""Tests for traffic client session breakdown."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, TrafficSessionState
from app.services.traffic.sessions import fetch_client_sessions
from app.services.ip_geo import normalize_client_ip


@pytest.fixture()
def sessions_db(tmp_path):
    db_path = tmp_path / "traffic_sessions.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    node = Node(name="local", host="127.0.0.1", port=9100, is_local=True, status=NodeStatus.online)
    db.add(node)
    db.commit()
    db.refresh(node)
    yield db, node
    db.close()


def test_normalize_client_ip():
    assert normalize_client_ip("udp4:203.0.113.10:51432") == "203.0.113.10"
    assert normalize_client_ip("203.0.113.10:51432") == "203.0.113.10"
    assert normalize_client_ip("[2001:db8::1]:1194") == "[2001:db8::1]"
    assert normalize_client_ip(None) == "неизвестно"


def test_fetch_client_sessions_groups_reconnects_by_ip(sessions_db):
    db, node = sessions_db
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    base_ts = int(datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc).timestamp())

    for idx, connected_ts in enumerate([base_ts, base_ts + 60, base_ts + 120]):
        db.add(
            TrafficSessionState(
                node_id=node.id,
                session_key=f"vpn-udp|alice|203.0.113.10:51432|10.8.0.5|{connected_ts}",
                profile="vpn-udp",
                common_name="alice",
                real_address="203.0.113.10:51432",
                virtual_address="10.8.0.5",
                connected_since_ts=connected_ts,
                last_bytes_received=1000 * (idx + 1),
                last_bytes_sent=500 * (idx + 1),
                is_active=idx == 2,
                last_seen_at=now,
                ended_at=None if idx == 2 else now,
            )
        )

    db.add(
        TrafficSessionState(
            node_id=node.id,
            session_key="vpn-udp|alice|198.51.100.2:60001|10.8.0.5|999",
            profile="vpn-udp",
            common_name="alice",
            real_address="198.51.100.2:60001",
            virtual_address="10.8.0.5",
            connected_since_ts=999,
            last_bytes_received=2000,
            last_bytes_sent=1000,
            is_active=False,
            last_seen_at=now,
            ended_at=now,
        )
    )
    db.commit()

    result = fetch_client_sessions(db, node.id, "alice", recent_limit=10)
    assert result["total_sessions"] == 4
    assert result["unique_sources"] == 2
    assert result["by_source"][0]["client_ip"] == "203.0.113.10"
    assert result["by_source"][0]["sessions_count"] == 3
    assert result["by_source"][1]["sessions_count"] == 1
    assert len(result["recent_sessions"]) == 4
