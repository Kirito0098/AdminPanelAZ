"""Tests for panel resource metrics model, service and API."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import PanelResourceSample, User, UserRole
from app.services.panel_resource_metrics import persist_sample, purge_old_samples, query_history
from app.services import panel_resource_metrics_worker as worker


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_persist_and_query_panel_history_buckets_samples(db_session):
    session = db_session
    now = datetime.utcnow()
    for i in range(6):
        sample = PanelResourceSample(
            backend_cpu_percent=10 + i,
            backend_memory_mb=100 + i * 10,
            backend_workers=1,
            total_panel_memory_mb=120 + i * 10,
            created_at=now - timedelta(minutes=30 - i * 5),
        )
        session.add(sample)
    session.commit()

    points, raw_count = query_history(session, "1d")
    assert raw_count == 6
    assert len(points) >= 1
    assert points[0]["backend_cpu_percent"] >= 10


def test_purge_old_panel_samples_removes_expired(db_session):
    session = db_session
    old = PanelResourceSample(
        backend_cpu_percent=1,
        backend_memory_mb=1,
        backend_workers=1,
        total_panel_memory_mb=1,
        created_at=datetime.utcnow() - timedelta(days=40),
    )
    fresh = PanelResourceSample(
        backend_cpu_percent=2,
        backend_memory_mb=2,
        backend_workers=1,
        total_panel_memory_mb=2,
        created_at=datetime.utcnow(),
    )
    session.add_all([old, fresh])
    session.commit()

    with patch("app.services.panel_resource_metrics.settings") as mock_settings:
        mock_settings.panel_resource_metrics_retention_days = 30
        deleted = purge_old_samples(session)

    assert deleted == 1
    assert session.query(PanelResourceSample).count() == 1


def test_panel_resource_worker_collects_sample():
    db = MagicMock()

    with patch.object(worker, "SessionLocal", return_value=db), patch.object(
        worker, "persist_sample"
    ) as persist, patch.object(worker, "purge_old_samples"):
        worker._collect_sample()

    persist.assert_called_once()
    assert persist.call_args.args[0] is db
    assert isinstance(persist.call_args.args[1], dict)


def test_panel_resource_history_api(db_session):
    session = db_session
    persist_sample(
        session,
        {
            "backend_cpu_percent": 12.5,
            "backend_memory_mb": 512,
            "backend_workers": 2,
            "nginx_memory_mb": 32,
            "total_panel_memory_mb": 580,
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

    client = TestClient(app)
    resp = client.get("/api/monitoring/panel-resource-history?period=1d")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["period"] == "1d"
    assert body["sample_count"] == 1
    assert len(body["points"]) == 1
    assert body["points"][0]["backend_memory_mb"] == 512


def test_panel_resource_current_api(db_session):
    from app.auth import get_current_user
    from app.main import app
    from app.database import get_db

    admin = User(
        username="admin",
        password_hash="hash",
        role=UserRole.admin,
        theme="dark",
    )
    live = {
        "timestamp": datetime.utcnow(),
        "backend_cpu_percent": 5.0,
        "backend_memory_mb": 300,
        "backend_rss_mb": 300,
        "backend_workers": 1,
        "nginx_memory_mb": None,
        "watchdog_memory_mb": 4,
        "frontend_dev_memory_mb": None,
        "total_panel_memory_mb": 304,
        "frontend_note": "Статические файлы раздаёт backend (FastAPI)",
    }

    app.dependency_overrides[get_current_user] = lambda: admin

    with patch("app.routers.monitoring.collect_panel_metrics", return_value=live):
        client = TestClient(app)
        resp = client.get("/api/monitoring/panel-resource-current")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["backend_workers"] == 1
    assert body["total_panel_memory_mb"] == 304


def test_panel_resource_api_requires_admin(db_session):
    from app.auth import get_current_user
    from app.main import app

    viewer = User(
        username="viewer",
        password_hash="hash",
        role=UserRole.viewer,
        theme="dark",
    )
    app.dependency_overrides[get_current_user] = lambda: viewer

    client = TestClient(app)
    resp = client.get("/api/monitoring/panel-resource-history?period=1d")

    app.dependency_overrides.clear()
    assert resp.status_code == 403
