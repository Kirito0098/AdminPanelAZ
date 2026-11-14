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


def test_user_history_endpoint_filters_by_target():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.routers import users as users_router
    from app.routers.users import require_admin

    db = _db()
    admin = User(username="admin", password_hash="x", role=UserRole.admin)
    target = User(username="ivan", password_hash="x", role=UserRole.user)
    db.add_all([admin, target])
    db.commit()
    db.refresh(admin)
    db.refresh(target)
    db.add_all(
        [
            UserActionLog(
                user_id=admin.id, username="admin", action="user_extend", target_user_id=target.id
            ),
            UserActionLog(
                user_id=admin.id, username="admin", action="user_suspend", target_user_id=target.id
            ),
            UserActionLog(
                user_id=admin.id, username="admin", action="user_other", target_user_id=None
            ),
        ]
    )
    db.commit()

    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: admin
    client = TestClient(app)

    r = client.get(f"/api/users/{target.id}/history")
    assert r.status_code == 200, r.text
    actions = [e["action"] for e in r.json()]
    assert "user_extend" in actions
    assert "user_suspend" in actions
    assert "user_other" not in actions

