"""Telegram link codes need the current password and never silently relink an account."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user_access_token, get_password_hash
from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import telegram_webhook
from app.services.app_setting_store import _set_setting
from app.services.telegram_link import create_link_code, redeem_link_code

PASSWORD = "Carol-pass-1"


class _Features:
    def is_enabled(self, _name):
        return True


@pytest.fixture
def db_factory(monkeypatch):
    monkeypatch.setattr(telegram_webhook, "get_feature_service", lambda: _Features())
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all(
        [
            User(username="carol", password_hash=get_password_hash(PASSWORD), role=UserRole.user, is_active=True),
            User(
                username="dave<b>",
                password_hash=get_password_hash(PASSWORD),
                role=UserRole.user,
                is_active=True,
                telegram_id="555",
            ),
        ]
    )
    _set_setting(db, "telegram_bot_token", "bot:token")
    db.commit()
    db.close()
    yield factory
    engine.dispose()


@pytest.fixture
def client(db_factory):
    app = FastAPI()
    app.include_router(telegram_webhook.router, prefix="/api")

    def _get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _auth(db_factory, username: str) -> dict[str, str]:
    db = db_factory()
    try:
        user = db.query(User).filter(User.username == username).one()
        return {"Authorization": f"Bearer {create_user_access_token(user)}"}
    finally:
        db.close()


def test_link_code_requires_current_password(client, db_factory):
    response = client.post(
        "/api/telegram/link-code", json={"current_password": "wrong"}, headers=_auth(db_factory, "carol")
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Неверный текущий пароль"


def test_link_code_issued_with_password(client, db_factory):
    response = client.post(
        "/api/telegram/link-code", json={"current_password": PASSWORD}, headers=_auth(db_factory, "carol")
    )
    assert response.status_code == 200
    assert len(response.json()["code"]) == 8


def test_link_code_get_is_gone(client, db_factory):
    assert client.get("/api/telegram/link-code", headers=_auth(db_factory, "carol")).status_code == 405


def test_linked_account_cannot_get_a_code(client, db_factory):
    response = client.post(
        "/api/telegram/link-code", json={"current_password": PASSWORD}, headers=_auth(db_factory, "dave<b>")
    )
    assert response.status_code == 409


def test_redeem_refuses_to_replace_another_telegram(db_factory):
    db = db_factory()
    try:
        dave = db.query(User).filter(User.username == "dave<b>").one()
        code, _ = create_link_code(db, dave)

        ok, message, user = redeem_link_code(db, code, "999")

        assert (ok, user) == (False, None)
        assert "Сначала отвяжите" in message
        db.refresh(dave)
        assert dave.telegram_id == "555"
    finally:
        db.close()


def test_redeem_same_telegram_succeeds_and_escapes_name(db_factory):
    db = db_factory()
    try:
        dave = db.query(User).filter(User.username == "dave<b>").one()
        code, _ = create_link_code(db, dave)

        ok, message, _user = redeem_link_code(db, code, "555")

        assert ok is True
        assert "dave&lt;b&gt;" in message
    finally:
        db.close()


def _users_client(db_factory):
    from app.routers import users as users_router

    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")

    def _get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def test_self_unlink_notifies_old_telegram(db_factory, monkeypatch):
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.services.telegram.send_tg_message",
        lambda _token, chat_id, text, **_k: sent.append((chat_id, text)) or True,
    )
    db = db_factory()
    dave_id = db.query(User).filter(User.username == "dave<b>").one().id
    db.close()

    response = _users_client(db_factory).patch(
        f"/api/users/{dave_id}", json={"telegram_id": ""}, headers=_auth(db_factory, "dave<b>")
    )

    assert response.status_code == 200
    assert len(sent) == 1
    chat_id, text = sent[0]
    assert chat_id == "555"
    assert "dave&lt;b&gt;" in text


def test_saving_same_telegram_id_sends_nothing(db_factory, monkeypatch):
    from app.services.telegram_link import notify_telegram_unlinked

    sent: list = []
    monkeypatch.setattr("app.services.telegram.send_tg_message", lambda *a, **k: sent.append(a) or True)
    db = db_factory()
    try:
        notify_telegram_unlinked(db, old_telegram_id="555", new_telegram_id="555", username="dave")
        notify_telegram_unlinked(db, old_telegram_id=None, new_telegram_id="555", username="dave")
    finally:
        db.close()

    assert sent == []
