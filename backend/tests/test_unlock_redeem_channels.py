"""Stage 3 Task 9: unlock redeem rate limit + Mini App channel."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_tg_mini_token, get_password_hash
from app.database import Base, get_db
from app.models import User, UserRole
from app.routers.tg_mini import me_redeem
from app.services.unlock_redeem_rate_limit import UnlockRedeemRateLimitService


def test_redeem_rate_limit_blocks_sixth_attempt():
    svc = UnlockRedeemRateLimitService()
    for _ in range(5):
        assert svc.consume("111") is None
    msg = svc.consume("111")
    assert msg is not None
    assert "10 минут" in msg


@pytest.fixture()
def db_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add(
        User(
            username="ivan",
            password_hash=get_password_hash("secret"),
            role=UserRole.user,
            is_active=True,
            telegram_id="111",
        )
    )
    db.commit()
    db.close()
    yield factory
    engine.dispose()


@pytest.fixture()
def client(db_factory, monkeypatch):
    app = FastAPI()
    app.include_router(me_redeem.router, prefix="/api/tg-mini")

    def _get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _headers(db_factory) -> dict[str, str]:
    with db_factory() as db:
        user = db.query(User).filter(User.username == "ivan").one()
        token = create_tg_mini_token(user.username, user.telegram_id or "111", token_version=user.token_version or 0)
    return {"Authorization": f"Bearer {token}"}


def test_tg_mini_redeem_requires_unlock_codes_toggle(client, db_factory, monkeypatch):
    monkeypatch.setattr(
        me_redeem,
        "get_feature_service",
        lambda: MagicMock(is_enabled=lambda key: key != "unlock_codes"),
    )
    r = client.post(
        "/api/tg-mini/me/redeem-code",
        json={"code": "AAAA-BBBB-CCCC"},
        headers=_headers(db_factory),
    )
    assert r.status_code == 403

