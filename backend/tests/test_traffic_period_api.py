"""API tests for traffic overview/chart period query params."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register ORM models on Base.metadata
from app.auth import get_current_user
from app.config import get_settings
from app.database import Base, get_db
from app.models import Node, NodeStatus, User, UserRole
from app.routers import traffic as traffic_router


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("TRAFFIC_SAMPLE_RETENTION_DAYS", "90")
    monkeypatch.setenv("LOCAL_ANTIZAPRET_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_node(db) -> Node:
    node = Node(
        name="node-1",
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=True,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _seed_user(db) -> User:
    user = User(username="owner", password_hash="hash", role=UserRole.admin, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def client(db):
    user = _seed_user(db)
    _seed_node(db)

    app = FastAPI()
    app.include_router(traffic_router.router)

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as c:
        yield c


def test_overview_rejects_range_beyond_retention(client):
    resp = client.get("/traffic/overview?from=2020-01-01&to=2026-09-10")
    assert resp.status_code == 400
    assert "90" in resp.json()["detail"]


def test_overview_preset_7d_ok(client):
    resp = client.get("/traffic/overview?period=7d&live=false")
    assert resp.status_code == 200
    body = resp.json()
    assert body["period_mode"] == "preset"
    assert body["period"] == "7d"
    assert "retention_days" in body
    assert body["retention_days"] == 90
    sample_row = body["rows"][0] if body["rows"] else {"traffic_period": 0}
    assert "traffic_30d" not in sample_row
    assert "traffic_period" in sample_row or not body["rows"]


def test_overview_default_period_30d(client):
    resp = client.get("/traffic/overview?live=false")
    assert resp.status_code == 200
    body = resp.json()
    assert body["period"] == "30d"
    assert body["period_mode"] == "preset"


def test_chart_custom_range_ignores_preset_range(client, db):
    node = db.query(Node).first()
    with patch.object(
        traffic_router,
        "fetch_traffic_chart",
        return_value={
            "client": "alice",
            "range": "custom",
            "bucket": "day",
            "protocol_filter": "all",
            "timezone": "UTC",
            "labels": [],
            "timestamps": [],
            "vpn_bytes": [],
            "antizapret_bytes": [],
            "openvpn_bytes": [],
            "wireguard_bytes": [],
            "amneziawg2_bytes": [],
            "total_vpn": 0,
            "total_antizapret": 0,
            "total": 0,
            "retention_days": 90,
        },
    ) as fetch_mock:
        resp = client.get(
            "/traffic/chart?client=alice&range=7d&from=2026-09-01&to=2026-09-05"
        )
    assert resp.status_code == 200
    assert resp.json()["range"] == "custom"
    assert resp.json()["retention_days"] == 90
    kwargs = fetch_mock.call_args.kwargs
    assert kwargs.get("period_window") is not None
    assert kwargs["period_window"].mode == "custom"
