"""Retention: переписка и карточки старше срока удаляются, свежие остаются."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserMessage, UserMessageCard, UserRole
from app.services.retention import run_retention_purge


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_purges_old_messages_and_cards(db):
    user = User(
        username="ivan",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        panel_login_enabled=True,
        telegram_id="111",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    old = datetime.utcnow() - timedelta(days=200)
    fresh = datetime.utcnow() - timedelta(days=10)
    db.add_all(
        [
            UserMessage(user_id=user.id, direction="in", text="старое", created_at=old),
            UserMessage(user_id=user.id, direction="in", text="новое", created_at=fresh),
            UserMessageCard(admin_chat_id="777", message_id=1, user_id=user.id, created_at=old),
            UserMessageCard(admin_chat_id="777", message_id=2, user_id=user.id, created_at=fresh),
        ]
    )
    db.commit()

    counts = run_retention_purge(db)

    assert counts["user_messages"] == 1
    assert counts["user_message_cards"] == 1
    assert [row.text for row in db.query(UserMessage).all()] == ["новое"]
    assert [row.message_id for row in db.query(UserMessageCard).all()] == [2]
