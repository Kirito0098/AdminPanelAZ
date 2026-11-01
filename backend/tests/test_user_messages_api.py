"""API чата: диалоги, счётчики, best-effort доставка, каскад при удалении."""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import require_admin
from app.database import Base, get_db
from app.models import User, UserMessage, UserRole
from app.routers import messages as messages_router


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    # Как в проде (database.py): без PRAGMA foreign_keys каскад ON DELETE не срабатывает.
    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def admin(db):
    user = User(
        username="admin", password_hash="x", role=UserRole.admin, is_active=True,
        panel_login_enabled=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def subscriber(db):
    user = User(
        username="ivan", password_hash="x", role=UserRole.user, is_active=True,
        panel_login_enabled=True, telegram_id="111",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def api(db, admin):
    app = FastAPI()
    app.include_router(messages_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(app)


def _msg(db, user, text, direction="in", read=False):
    row = UserMessage(
        user_id=user.id, direction=direction, text=text,
        read_by_admin_at=datetime.utcnow() if read else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_threads_return_last_message_and_unread(api, db, subscriber):
    _msg(db, subscriber, "первое")
    _msg(db, subscriber, "второе")

    response = api.get("/api/messages/threads")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["user_id"] == subscriber.id
    assert body[0]["last_text"] == "второе"
    assert body[0]["last_direction"] == "in"
    assert body[0]["unread_count"] == 2


def test_threads_unread_filter(api, db, subscriber):
    _msg(db, subscriber, "прочитано", read=True)

    assert api.get("/api/messages/threads?unread=1").json() == []
    assert api.get("/api/messages/unread-count").json() == {"count": 0}


def test_mark_read_clears_unread(api, db, subscriber):
    _msg(db, subscriber, "вопрос")

    assert api.post(f"/api/messages/{subscriber.id}/read").json() == {"marked": 1}
    assert api.get("/api/messages/unread-count").json() == {"count": 0}


def test_messages_cursor_pagination(api, db, subscriber):
    first = _msg(db, subscriber, "1")
    second = _msg(db, subscriber, "2")

    assert [item["text"] for item in api.get(f"/api/messages/{subscriber.id}?limit=1").json()] == ["2"]

    older = api.get(f"/api/messages/{subscriber.id}?before_id={second.id}").json()
    assert older[0]["id"] == first.id


def test_reply_saved_and_delivered(api, db, subscriber, monkeypatch):
    monkeypatch.setattr(
        "app.services.user_messages._get_setting", lambda db, key, default=None: "bot-token"
    )
    sent = []
    monkeypatch.setattr(
        "app.services.user_messages.send_tg_message_result",
        lambda token, chat_id, text: (sent.append((chat_id, text)) or (True, None)),
    )

    response = api.post(f"/api/messages/{subscriber.id}", json={"text": "Здравствуйте"})

    assert response.status_code == 200, response.text
    assert response.json()["delivered"] is True
    assert sent and sent[0][0] == "111"
    assert "Здравствуйте" in sent[0][1]
    assert db.query(UserMessage).filter_by(direction="out").count() == 1


def test_reply_kept_when_bot_blocked(api, db, subscriber, monkeypatch):
    monkeypatch.setattr(
        "app.services.user_messages._get_setting", lambda db, key, default=None: "bot-token"
    )
    monkeypatch.setattr(
        "app.services.user_messages.send_tg_message_result", lambda *a, **k: (False, 403)
    )

    body = api.post(f"/api/messages/{subscriber.id}", json={"text": "Ответ"}).json()

    assert body["delivered"] is False
    assert "заблокирован" in body["warning"]
    assert db.query(UserMessage).count() == 1


def test_reply_requires_existing_user(api):
    assert api.post("/api/messages/9999", json={"text": "нет"}).status_code == 404


def test_reply_validates_length(api, subscriber):
    assert api.post(f"/api/messages/{subscriber.id}", json={"text": "x" * 4097}).status_code == 422
    assert api.post(f"/api/messages/{subscriber.id}", json={"text": ""}).status_code == 422


def test_messages_cascade_on_user_delete(db, subscriber):
    _msg(db, subscriber, "удалится вместе с абонентом")

    db.delete(subscriber)
    db.commit()

    assert db.query(UserMessage).count() == 0


def test_messages_paths_are_guarded_by_module():
    from app.services.feature_guards import _modules_for_path

    assert _modules_for_path("/api/messages/threads") == ("user_messaging",)
    assert _modules_for_path("/api/messages/42") == ("user_messaging",)
