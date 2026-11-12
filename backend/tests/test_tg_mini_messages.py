"""Mini App chat: доступ админа, фича-гард и изоляция диалога абонента."""

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_tg_mini_user
from app.database import Base, get_db
from app.models import User, UserMessage, UserRole
from app.routers.tg_mini import messages as tg_messages
from app.routers.tg_mini.messages import router as messages_router
from app.services.feature_guards import module_disabled_message


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
        engine.dispose()


class _Features:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def is_enabled(self, key: str) -> bool:
        return self.enabled


@pytest.fixture(autouse=True)
def messaging_enabled(monkeypatch):
    monkeypatch.setattr(tg_messages, "get_feature_service", lambda: _Features(True))


@pytest.fixture()
def client(db):
    app = FastAPI()
    app.include_router(messages_router, prefix="/api/tg-mini")

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _user(db, username: str, role: UserRole = UserRole.user, telegram_id: str = "111") -> User:
    user = User(
        username=username,
        password_hash="x",
        role=role,
        is_active=True,
        panel_login_enabled=True,
        telegram_id=telegram_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_threads_require_admin(client, db):
    user = _user(db, "ivan")
    client.app.dependency_overrides[get_tg_mini_user] = lambda: user

    response = client.get("/api/tg-mini/messages/threads")

    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text


def test_feature_disabled_blocks_chat(client, db, monkeypatch):
    monkeypatch.setattr(tg_messages, "get_feature_service", lambda: _Features(False))
    user = _user(db, "ivan")
    client.app.dependency_overrides[get_tg_mini_user] = lambda: user

    response = client.get("/api/tg-mini/me/messages")

    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
    assert response.json()["detail"] == module_disabled_message("user_messaging")


def test_me_messages_only_own_dialog(client, db):
    ivan = _user(db, "ivan", telegram_id="111")
    petr = _user(db, "petr", telegram_id="222")
    db.add_all(
        [
            UserMessage(user_id=ivan.id, direction="in", text="от ивана"),
            UserMessage(user_id=ivan.id, direction="out", text="ответ ивану"),
            UserMessage(user_id=petr.id, direction="in", text="от петра"),
        ]
    )
    db.commit()
    client.app.dependency_overrides[get_tg_mini_user] = lambda: ivan

    response = client.get("/api/tg-mini/me/messages")

    assert response.status_code == status.HTTP_200_OK, response.text
    assert {row["text"] for row in response.json()} == {"от ивана", "ответ ивану"}
