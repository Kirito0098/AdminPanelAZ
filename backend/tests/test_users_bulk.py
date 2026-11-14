"""Bulk user operations: guards + report."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import users as users_router
from app.routers.users import require_admin


class _FeatureService:
    def is_enabled(self, key: str) -> bool:
        return True


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)()


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr("app.routers.users.get_feature_service", lambda: _FeatureService())
    adapter = MagicMock()
    for name in (
        "read_config_file",
        "read_profile_file",
        "write_config_file",
        "ensure_openvpn_ban_check",
        "add_openvpn_client",
        "delete_openvpn_client",
        "awg2_add_client",
        "awg2_delete_client",
        "add_wireguard_client",
        "delete_wireguard_client",
    ):
        getattr(adapter, name).return_value = None
    adapter.get_profile_files.return_value = []
    monkeypatch.setattr("app.services.user_blocks.get_adapter_for_node", lambda node: adapter)
    monkeypatch.setattr("app.services.config_provisioning.get_adapter_for_node", lambda node: adapter)


def _user(db, username, role=UserRole.user):
    u = User(username=username, password_hash="x", role=role, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db):
    return _user(db, "admin", UserRole.admin)


@pytest.fixture
def client(db, admin):
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(app)


def test_bulk_requires_admin(db):
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    r = TestClient(app).post(
        "/api/users/bulk", json={"action": "extend", "user_ids": [1], "days": 30}
    )
    assert r.status_code in (401, 403)


def test_bulk_extend_adds_days(client, db):
    a = _user(db, "alice")
    b = _user(db, "bob")
    r = client.post(
        "/api/users/bulk", json={"action": "extend", "user_ids": [a.id, b.id], "days": 30}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["succeeded"] == 2
    assert body["failed"] == []
    db.refresh(a)
    db.refresh(b)
    assert a.access_until is not None
    assert b.access_until is not None


def test_bulk_suspend_reports_admin_failure(client, db, admin):
    u = _user(db, "carol")
    r = client.post("/api/users/bulk", json={"action": "suspend", "user_ids": [u.id, admin.id]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded"] == 1
    assert body["total"] == 2
    assert len(body["failed"]) == 1
    db.refresh(u)
    assert u.suspended_at is not None
