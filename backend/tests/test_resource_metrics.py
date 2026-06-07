"""Tests for node resource metrics model, service and API."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeResourceSample, NodeStatus, User, UserRole
from app.services.resource_metrics import (
    metrics_to_sample_fields,
    persist_sample,
    purge_old_samples,
    query_history,
)
from app.services import resource_metrics_worker as worker


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test.db"
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


def test_metrics_to_sample_fields_parses_load_average():
    metrics = {
        "cpu_percent": 12.5,
        "memory_percent": 44.2,
        "memory_used": 2 * 1024 * 1024 * 1024,
        "memory_total": 8 * 1024 * 1024 * 1024,
        "disk_percent": 61.0,
        "load_average": {"load_1m": 0.42, "load_5m": 0.31, "load_15m": 0.22},
    }
    fields = metrics_to_sample_fields(metrics)
    assert fields["cpu_percent"] == 12.5
    assert fields["memory_used_mb"] == 2048
    assert fields["memory_total_mb"] == 8192
    assert fields["load_1"] == 0.42
    assert fields["load_15"] == 0.22


def test_persist_and_query_history_buckets_samples(db_session):
    session, node = db_session
    now = datetime.utcnow()
    for i in range(6):
        sample = NodeResourceSample(
            node_id=node.id,
            cpu_percent=10 + i,
            memory_percent=20 + i,
            memory_used_mb=1000 + i,
            memory_total_mb=8000,
            disk_percent=30 + i,
            load_1=0.5,
            created_at=now - timedelta(minutes=30 - i * 5),
        )
        session.add(sample)
    session.commit()

    points, raw_count = query_history(session, node.id, "1d")
    assert raw_count == 6
    assert len(points) >= 1
    assert points[0]["cpu_percent"] >= 10


def test_purge_old_samples_removes_expired(db_session):
    session, node = db_session
    old = NodeResourceSample(
        node_id=node.id,
        cpu_percent=1,
        memory_percent=1,
        memory_used_mb=1,
        memory_total_mb=1,
        disk_percent=1,
        created_at=datetime.utcnow() - timedelta(days=40),
    )
    fresh = NodeResourceSample(
        node_id=node.id,
        cpu_percent=2,
        memory_percent=2,
        memory_used_mb=2,
        memory_total_mb=2,
        disk_percent=2,
        created_at=datetime.utcnow(),
    )
    session.add_all([old, fresh])
    session.commit()

    with patch("app.services.resource_metrics.settings") as mock_settings:
        mock_settings.resource_metrics_retention_days = 30
        deleted = purge_old_samples(session)

    assert deleted == 1
    remaining = session.query(NodeResourceSample).count()
    assert remaining == 1


def test_resource_metrics_worker_collects_for_all_nodes():
    node = MagicMock()
    node.id = 3
    node.name = "vpn"

    adapter = MagicMock()
    adapter.get_server_metrics.return_value = {
        "cpu_percent": 5,
        "memory_percent": 10,
        "memory_used": 1024,
        "memory_total": 2048,
        "disk_percent": 20,
        "load_average": {},
    }

    db = MagicMock()
    db.query.return_value.all.return_value = [node]

    with patch.object(worker, "SessionLocal", return_value=db), patch.object(
        worker, "get_adapter_for_node", return_value=adapter
    ), patch.object(worker, "persist_sample") as persist, patch.object(worker, "purge_old_samples"):
        worker._collect_all_nodes()

    persist.assert_called_once()
    adapter.get_server_metrics.assert_called_once()


def test_monitoring_resource_history_api(db_session):
    session, node = db_session
    persist_sample(
        session,
        node.id,
        {
            "cpu_percent": 33.3,
            "memory_percent": 55.5,
            "memory_used": 1024 * 1024 * 1024,
            "memory_total": 4 * 1024 * 1024 * 1024,
            "disk_percent": 70.0,
            "load_average": {"load_1m": 1.1},
        },
    )

    from app.auth import get_current_user
    from app.main import app
    from app.database import get_db

    admin = User(
        username="admin",
        password_hash="hash",
        role=UserRole.admin,
        theme="dark",
    )

    def override_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin

    with patch("app.routers.monitoring.get_active_node", return_value=node):
        client = TestClient(app)
        resp = client.get("/api/monitoring/resource-history?period=1d")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["node_id"] == node.id
    assert body["period"] == "1d"
    assert body["sample_count"] == 1
    assert len(body["points"]) == 1
    assert body["points"][0]["cpu_percent"] == 33.3
