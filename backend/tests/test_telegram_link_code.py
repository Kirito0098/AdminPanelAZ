"""Telegram link codes need the current password and never silently relink an account."""

from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user_access_token, get_password_hash
from app.config import get_settings
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
    code = response.json()["code"]
    assert len(code) == 12
    assert all(char in "0123456789abcdef" for char in code)


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


# --- H1: коды хранятся HMAC-хэшем, legacy-плейнтекст ещё принимается ---


def _stored_codes(db) -> dict:
    import json

    from app.services.app_setting_store import _get_setting

    return json.loads(_get_setting(db, "telegram_link_codes", "{}"))


def test_new_code_is_stored_as_sha256_hash(db_factory):
    db = db_factory()
    try:
        carol = db.query(User).filter(User.username == "carol").one()
        code, _ttl = create_link_code(db, carol)

        stored = _stored_codes(db)
        expected = hmac.new(
            get_settings().secret_key.encode(), code.encode(), hashlib.sha256
        ).hexdigest()
        assert list(stored) == [f"sha256:{expected}"]
        key = next(iter(stored))
        assert key.startswith("sha256:")
        assert len(key) == len("sha256:") + 64
        assert all(char in "0123456789abcdef" for char in key[len("sha256:") :])
        assert code not in stored
    finally:
        db.close()


def test_legacy_plaintext_code_is_still_accepted(db_factory):
    import json
    from datetime import datetime, timedelta, timezone

    db = db_factory()
    try:
        carol = db.query(User).filter(User.username == "carol").one()
        legacy = "abc123def456"
        _set_setting(
            db,
            "telegram_link_codes",
            json.dumps(
                {
                    legacy: {
                        "user_id": carol.id,
                        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                    }
                }
            ),
        )
        db.commit()

        ok, message, user = redeem_link_code(db, legacy, "777")

        assert ok is True, message
        assert user is not None and user.id == carol.id
        assert _stored_codes(db) == {}
    finally:
        db.close()


def test_wrong_code_does_not_link(db_factory):
    db = db_factory()
    try:
        ok, _message, user = redeem_link_code(db, "deadbeefcafe", "777")

        assert (ok, user) == (False, None)
        assert db.query(User).filter(User.telegram_id == "777").first() is None
    finally:
        db.close()


def test_expired_hashed_code_is_rejected(db_factory):
    import json
    from datetime import datetime, timedelta, timezone

    from app.services.telegram_link import _code_hash

    db = db_factory()
    try:
        carol = db.query(User).filter(User.username == "carol").one()
        code = "0badc0de1234"
        _set_setting(
            db,
            "telegram_link_codes",
            json.dumps(
                {
                    _code_hash(code): {
                        "user_id": carol.id,
                        "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                    }
                }
            ),
        )
        db.commit()

        ok, message, _user = redeem_link_code(db, code, "777")

        assert ok is False
        assert "истёк" in message
        assert _stored_codes(db) == {}
    finally:
        db.close()


def test_one_active_code_per_user_survives_hashing(db_factory):
    db = db_factory()
    try:
        carol = db.query(User).filter(User.username == "carol").one()
        first, _ = create_link_code(db, carol)
        second, _ = create_link_code(db, carol)

        stored = _stored_codes(db)
        assert len(stored) == 1
        assert int(next(iter(stored.values()))["user_id"]) == carol.id

        ok_old, _message, _user = redeem_link_code(db, first, "777")
        assert ok_old is False

        ok_new, message, _user = redeem_link_code(db, second, "777")
        assert ok_new is True, message
    finally:
        db.close()
