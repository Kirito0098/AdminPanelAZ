"""Closed-access banner states for portal / Mini App (Stage 3, Task 11)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_tg_mini_user
from app.database import Base, get_db
from app.models import User
from app.routers.tg_mini import me_configs
from app.services.user_closed_access import (
    closed_access_payload,
    closed_access_view,
    grace_hold_view,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _user(db, **kwargs) -> User:
    payload = {
        "username": "ivan",
        "password_hash": "x",
        "role": "user",
        "is_active": True,
        "can_create_configs": True,
        "panel_login_enabled": True,
        "provision_state": "unmanaged",
    }
    payload.update(kwargs)
    user = User(**payload)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def test_closed_access_none_when_access_open(db):
    user = _user(db, access_until=NOW + timedelta(days=30))
    assert closed_access_view(user, now=NOW) is None


def test_closed_access_expired(db):
    user = _user(db, access_until=NOW - timedelta(days=2))
    view = closed_access_view(user, now=NOW)
    assert view is not None
    assert view["state"] == "expired"
    assert view["access_until"] is not None


def test_closed_access_expiring_within_7_days(db):
    user = _user(db, access_until=NOW + timedelta(days=3))
    view = closed_access_view(user, now=NOW)
    assert view is not None
    assert view["state"] == "expiring"


def test_closed_access_suspended_hides_reason_unless_allowed(db):
    user = _user(
        db,
        suspended_at=NOW - timedelta(hours=1),
        suspend_reason="неоплата",
        suspend_reason_visible=False,
    )
    view = closed_access_view(user, now=NOW)
    assert view is not None
    assert view["state"] == "suspended"
    assert view["reason"] is None

    user.suspend_reason_visible = True
    db.commit()
    view = closed_access_view(user, now=NOW)
    assert view["reason"] == "неоплата"


def test_closed_access_suspended_outranks_traffic_and_expiry(db):
    user = _user(
        db,
        suspended_at=NOW - timedelta(hours=1),
        traffic_limit_blocked=True,
        access_until=NOW - timedelta(days=5),
    )
    view = closed_access_view(user, now=NOW)
    assert view is not None
    assert view["state"] == "suspended"


def test_closed_access_traffic_limit(db):
    user = _user(db, traffic_limit_blocked=True, access_until=NOW + timedelta(days=10))
    view = closed_access_view(user, now=NOW)
    assert view is not None
    assert view["state"] == "traffic_limit"


def test_closed_access_payload_adds_actions(db):
    user = _user(db, access_until=NOW - timedelta(days=1))
    payload = closed_access_payload(db, user, now=NOW)
    assert payload is not None
    assert payload["state"] == "expired"
    assert "requests_enabled" in payload
    assert "contact_url" in payload


def test_grace_hold_view_counts_elapsed_months(db):
    user = _user(db, access_until=NOW - timedelta(days=95))
    hold = grace_hold_view(user, 3, now=NOW)
    assert hold is not None
    assert hold["elapsed_months"] == 3
    assert hold["limit_months"] == 3


def test_grace_hold_view_none_when_grace_off(db):
    user = _user(db, access_until=NOW - timedelta(days=95))
    assert grace_hold_view(user, 0, now=NOW) is None


def test_grace_hold_view_none_before_expiry(db):
    user = _user(db, access_until=NOW + timedelta(days=1))
    assert grace_hold_view(user, 3, now=NOW) is None


def test_tg_mini_me_configs_returns_closed_access(db):
    """Mini App получает состояние закрытого доступа вместе со списком конфигов."""
    user = _user(db, access_until=NOW - timedelta(days=1), telegram_id="111")
    app = FastAPI()
    app.include_router(me_configs.router, prefix="/api/tg-mini")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_tg_mini_user] = lambda: user
    client = TestClient(app)

    r = client.get("/api/tg-mini/me/configs")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["configs"] == []
    assert payload["closed_access"] is not None
    assert payload["closed_access"]["state"] == "expired"
    assert "requests_enabled" in payload["closed_access"]
    assert "contact_url" in payload["closed_access"]


def test_tg_mini_me_configs_closed_access_null_when_open(db):
    user = _user(db, access_until=NOW + timedelta(days=30), telegram_id="111")
    app = FastAPI()
    app.include_router(me_configs.router, prefix="/api/tg-mini")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_tg_mini_user] = lambda: user
    client = TestClient(app)

    r = client.get("/api/tg-mini/me/configs")
    assert r.status_code == 200, r.text
    assert r.json()["closed_access"] is None
