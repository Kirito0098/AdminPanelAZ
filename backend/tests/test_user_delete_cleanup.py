"""User deletion cleanup must finish or fail loudly — never wedge the row in pending_deletion."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, User, UserActionLog, UserRole, VpnConfig, VpnType
from app.services import user_provisioning as provisioning


@pytest.fixture()
def factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _record):  # noqa: ANN001 — сигнатура события SQLAlchemy
        # Как в проде (database.py): без этого тесты не видят FK-конфликтов удаления.
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    monkeypatch.setattr(provisioning, "SessionLocal", make)
    monkeypatch.setattr("app.services.client_portal.revoke_creator_portal_links", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.refresh_token.invalidate_user_sessions", lambda *_a, **_k: None)

    class _Sessions:
        def revoke_user_sessions(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr("app.services.active_web_session.active_web_session_service", _Sessions())
    monkeypatch.setattr(provisioning, "is_in_plan_config", lambda *_a, **_k: True)
    try:
        yield make
    finally:
        engine.dispose()


def _seed(make, *, telegram_id: str | None = "777") -> int:
    with make() as db:
        admin = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
        user = User(
            username="test",
            password_hash="x",
            role=UserRole.user,
            is_active=True,
            telegram_id=telegram_id,
            provision_state="pending_deletion",
        )
        db.add_all([admin, user])
        node = Node(name="nl-1", host="10.0.0.1", node_kind="vpn")
        db.add(node)
        db.commit()
        db.add(
            VpnConfig(
                node_id=node.id,
                client_name="test-wg",
                vpn_type=VpnType.wireguard,
                owner_id=user.id,
            )
        )
        db.commit()
        return user.id


def _capture_updates(monkeypatch) -> list[dict]:
    updates: list[dict] = []

    def _update(_task_id, **kwargs):
        updates.append(kwargs)

    monkeypatch.setattr(provisioning.background_task_service, "update_background_task", _update)
    return updates


def test_cleanup_marks_the_task_failed_and_keeps_the_user_pending(factory, monkeypatch):
    user_id = _seed(factory)
    updates = _capture_updates(monkeypatch)

    def _boom(*_args, **_kwargs):
        raise HTTPException(status_code=500, detail="Please check if client exists")

    monkeypatch.setattr(provisioning, "deprovision_config", _boom)

    result = provisioning.run_user_delete_cleanup("task-1", user_id, "admin")

    assert result["success"] is False
    assert updates and updates[-1]["status"] == "failed"
    with factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        assert user.provision_state == "pending_deletion"
        assert user.is_active is False
        assert user.telegram_id is None


def test_cleanup_deletes_the_user_when_every_config_is_gone(factory, monkeypatch):
    user_id = _seed(factory)
    updates = _capture_updates(monkeypatch)
    monkeypatch.setattr(provisioning, "deprovision_config", lambda *_a, **_k: None)

    result = provisioning.run_user_delete_cleanup("task-2", user_id, "admin")

    assert result["success"] is True
    assert updates and updates[-1]["status"] == "completed"
    with factory() as db:
        assert db.get(User, user_id) is None


def test_cleanup_deletes_user_referenced_by_action_log_as_target(factory, monkeypatch):
    """Аудит с target_user_id не должен блокировать удаление (FK без ON DELETE)."""
    user_id = _seed(factory)
    updates = _capture_updates(monkeypatch)
    monkeypatch.setattr(provisioning, "deprovision_config", lambda *_a, **_k: None)
    with factory() as db:
        admin = db.query(User).filter(User.role == UserRole.admin).one()
        db.add(
            UserActionLog(
                user_id=admin.id,
                username=admin.username,
                action="user_suspend",
                details="target=test",
                target_user_id=user_id,
            )
        )
        db.add(
            UserActionLog(
                user_id=user_id,
                username="test",
                action="telegram_link",
                details="telegram_id=777",
            )
        )
        db.commit()

    result = provisioning.run_user_delete_cleanup("task-3", user_id, "admin")

    assert result["success"] is True
    assert updates and updates[-1]["status"] == "completed"
    with factory() as db:
        assert db.get(User, user_id) is None
        suspend_log = db.query(UserActionLog).filter(UserActionLog.action == "user_suspend").one()
        assert suspend_log.target_user_id is None
        assert suspend_log.user_id is not None
        link_log = db.query(UserActionLog).filter(UserActionLog.action == "telegram_link").one()
        assert link_log.user_id is None
        assert link_log.username == "test"
