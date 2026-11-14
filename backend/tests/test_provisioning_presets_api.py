"""Preset CRUD returns lists, not raw JSON strings stored in the ORM."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import require_admin
from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import users as users_router


def _make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


def _make_admin(db) -> User:
    user = User(username="admin", password_hash="hash", role=UserRole.admin, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _client(Session, monkeypatch) -> TestClient:
    db = Session()
    admin = _make_admin(db)
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    monkeypatch.setattr(
        users_router, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda key: True)
    )

    def _override_db():
        request_db = Session()
        try:
            yield request_db
        finally:
            request_db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = lambda: admin
    db.close()
    return TestClient(app)


def test_preset_create_list_update_round_trip(monkeypatch):
    engine, Session = _make_db()
    client = _client(Session, monkeypatch)

    with client:
        created = client.post(
            "/api/users/presets",
            json={
                "name": "Домашний",
                "node_ids": [1, 2],
                "protocols": ["openvpn", "wireguard"],
                "config_count": 2,
                "is_default": True,
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["node_ids"] == [1, 2]
        assert body["protocols"] == ["openvpn", "wireguard"]
        assert body["is_default"] is True

        listed = client.get("/api/users/presets")
        assert listed.status_code == 200, listed.text
        rows = listed.json()
        assert len(rows) == 1
        assert rows[0]["id"] == body["id"]
        assert rows[0]["node_ids"] == [1, 2]
        assert rows[0]["protocols"] == ["openvpn", "wireguard"]

        updated = client.put(
            f"/api/users/presets/{body['id']}",
            json={"node_ids": [3], "protocols": ["amneziawg"]},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["node_ids"] == [3]
        assert updated.json()["protocols"] == ["amneziawg"]

    engine.dispose()
