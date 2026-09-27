"""Active user portal token uniqueness per user_id."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserPortalToken, UserRole


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_user_portal_tokens_active_user
                ON user_portal_tokens (user_id)
                WHERE revoked_at IS NULL
                """
            )
        )
    Session = sessionmaker(bind=engine)
    session = Session()
    user = User(username="alice", password_hash="hash", role=UserRole.user)
    session.add(user)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_cannot_insert_two_active_tokens_same_user(db_session):
    user_id = db_session.query(User).one().id
    db_session.add(UserPortalToken(token="tok-a", user_id=user_id))
    db_session.commit()
    db_session.add(UserPortalToken(token="tok-b", user_id=user_id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_revoked_user_token_allows_new_active(db_session):
    user_id = db_session.query(User).one().id
    old = UserPortalToken(token="tok-old", user_id=user_id)
    db_session.add(old)
    db_session.commit()
    old.revoked_at = old.created_at
    db_session.commit()
    db_session.add(UserPortalToken(token="tok-new", user_id=user_id))
    db_session.commit()
    active = (
        db_session.query(UserPortalToken)
        .filter(
            UserPortalToken.user_id == user_id,
            UserPortalToken.revoked_at.is_(None),
        )
        .all()
    )
    assert len(active) == 1
    assert active[0].token == "tok-new"
