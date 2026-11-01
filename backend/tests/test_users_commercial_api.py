"""Users commercial UX: log_action target_user_id + list fields."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserActionLog, UserRole
from app.services.action_log import log_action


def _db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_log_action_sets_target_user_id():
    db = _db()
    actor = User(username="admin", password_hash="x", role=UserRole.admin)
    db.add(actor)
    db.commit()
    row = log_action(
        db, action="user_suspend", username="admin", user_id=actor.id, target_user_id=123
    )
    assert row is not None
    assert isinstance(row, UserActionLog)
    assert row.target_user_id == 123
