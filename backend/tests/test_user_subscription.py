from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, UserRole
from app.services import user_subscription as usub


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_user_subscription_expired_null_is_unlimited(db):
    user = User(username="u1", password_hash="x", role=UserRole.user, is_active=True)
    db.add(user)
    db.commit()
    assert usub.user_subscription_expired(user) is False


def test_user_subscription_expired_past(db):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    user = User(
        username="u2",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=past.replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    assert usub.user_subscription_expired(user) is True


def test_user_subscription_expired_future(db):
    future = datetime.now(timezone.utc) + timedelta(days=7)
    user = User(
        username="u3",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=future.replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    assert usub.user_subscription_expired(user) is False
