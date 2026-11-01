"""Unlock code create + optional Telegram delivery."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import unlock_codes as unlock_router
from app.routers.unlock_codes import require_admin


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


def _make(db, username, role=UserRole.user, telegram_id=None):
    u = User(
        username=username, password_hash="x", role=role, is_active=True, telegram_id=telegram_id
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db):
    return _make(db, "admin", UserRole.admin)


def _client(db, admin):
    app = FastAPI()
    app.include_router(unlock_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(app)


def _patch(monkeypatch, calls):
    monkeypatch.setattr("app.routers.unlock_codes.get_feature_service", lambda: _FeatureService())
    monkeypatch.setattr("app.routers.unlock_codes._get_setting", lambda db, key: "token")

    def fake_send(bot_token, chat_id, text, **kwargs):
        calls.append((bot_token, str(chat_id), text))
        return True

    monkeypatch.setattr("app.routers.unlock_codes.send_tg_message", fake_send)


def test_create_sends_to_bound_telegram(db, admin, monkeypatch):
    target = _make(db, "ivan", telegram_id="555")
    calls = []
    _patch(monkeypatch, calls)
    r = _client(db, admin).post(
        "/api/unlock-codes",
        json={
            "grant_days": 30,
            "protocols": ["openvpn"],
            "mode": "single",
            "allowed_client_names": ["ivan"],
            "send_to_user_id": target.id,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent_to_telegram"] is True
    assert body["code"]
    assert len(calls) == 1
    assert calls[0][1] == "555"
    assert body["code"] in calls[0][2]


def test_create_without_telegram_does_not_send(db, admin, monkeypatch):
    target = _make(db, "bob", telegram_id=None)
    calls = []
    _patch(monkeypatch, calls)
    r = _client(db, admin).post(
        "/api/unlock-codes",
        json={
            "grant_days": 30,
            "protocols": ["openvpn"],
            "mode": "single",
            "send_to_user_id": target.id,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["sent_to_telegram"] is False
    assert calls == []
