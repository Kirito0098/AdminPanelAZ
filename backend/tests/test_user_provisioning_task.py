"""Stage 1 Task 5: user_provision background task (subject-key exclusivity, 409 confirm_deletions, per-node skip)."""

from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, UserNodeAssignment, VpnConfig, VpnType
from app.services.admin_notify import admin_notify_service
from app.services.background_tasks import background_task_service
from app.services.user_provisioning import (
    enqueue_user_provision,
    run_user_provision_task,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _node(db, *, name, status=NodeStatus.online):
    node = Node(
        name=name,
        host="127.0.0.1",
        port=9100,
        api_key_hash="h",
        api_key_encrypted="e",
        status=status,
        is_local=True,
        node_kind="vpn",
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _user(
    db,
    *,
    username,
    client_base_name,
    plan_config_indexes,
    desired_protocols=["wireguard"],
    access_until=None,
):
    import json

    user = User(
        username=username,
        password_hash="x",
        role=UserRole.user,
        client_base_name=client_base_name,
        plan_config_indexes=json.dumps(plan_config_indexes),
        desired_protocols=json.dumps(desired_protocols),
        access_until=access_until,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _assign(db, user, node):
    assignment = UserNodeAssignment(user_id=user.id, node_id=node.id)
    db.add(assignment)
    db.commit()
    return assignment


def _config(db, *, node, client_name, vpn_type=VpnType.wireguard, owner):
    config = VpnConfig(
        node_id=node.id, client_name=client_name, vpn_type=vpn_type, owner_id=owner.id
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@pytest.fixture()
def patch_sessions(monkeypatch, db):
    """Route background_tasks and user_provisioning SessionLocal at the in-memory test DB."""
    TestSessionLocal = sessionmaker(bind=db.bind)
    monkeypatch.setattr("app.services.background_tasks.SessionLocal", lambda: TestSessionLocal())
    monkeypatch.setattr("app.services.user_provisioning.SessionLocal", lambda: TestSessionLocal())


@pytest.fixture()
def features_on(monkeypatch):
    class _Service:
        def is_enabled(self, key):
            return True

    monkeypatch.setattr("app.services.user_provisioning.get_feature_service", lambda: _Service())


@pytest.fixture()
def no_enqueue(monkeypatch):
    """Do not spawn background threads; record submits instead."""
    calls = []

    def fake_submit(fn, *args, **kwargs):
        calls.append((fn, args, kwargs))

    monkeypatch.setattr("app.services.user_provisioning._submit_in_current_context", fake_submit)
    return calls


@pytest.fixture()
def notify_mock(monkeypatch):
    with patch.object(admin_notify_service, "send") as m:
        yield m


def test_find_active_task_by_subject_key(db, patch_sessions):
    task_one = background_task_service.create_queued_task(
        "user_provision", "one", created_by_username="admin", subject_key="user:1"
    )
    task_two = background_task_service.create_queued_task(
        "user_provision", "two", created_by_username="admin", subject_key="user:2"
    )

    found = background_task_service.find_active_task("user_provision", subject_key="user:1")
    assert found is not None
    assert found.id == task_one
    assert found.subject_key == "user:1"

    found_other = background_task_service.find_active_task("user_provision", subject_key="user:2")
    assert found_other is not None
    assert found_other.id == task_two

    # Without subject_key it returns the most recent active task regardless of user.
    found_any = background_task_service.find_active_task("user_provision")
    assert found_any is not None
    assert found_any.id in {task_one, task_two}


def test_enqueue_user_provision_409_confirm_deletions_without_flag(
    db, patch_sessions, features_on, no_enqueue
):
    ivan = _user(db, username="ivan", client_base_name="ivan", plan_config_indexes=[1, 2])
    germany = _node(db, name="Germany")
    _assign(db, ivan, germany)
    # Make plan have a deletion: indexes [1] while ivan-2 config exists.
    ivan.plan_config_indexes = "[1]"
    db.commit()
    _config(db, node=germany, client_name="ivan-2", vpn_type=VpnType.wireguard, owner=ivan)

    with pytest.raises(HTTPException) as exc:
        enqueue_user_provision(db, user_id=ivan.id, actor_username="admin", confirm_deletions=False)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "confirm_deletions"

    # With the flag it records a background submit for a new task.
    task = enqueue_user_provision(db, user_id=ivan.id, actor_username="admin", confirm_deletions=True)
    assert task is not None
    assert task.task_type == "user_provision"
    assert task.subject_key == f"user:{ivan.id}"
    assert len(no_enqueue) == 1


def test_enqueue_user_provision_409_access_expired(db, patch_sessions, features_on):
    from datetime import datetime, timedelta, timezone

    ivan = _user(
        db,
        username="ivan",
        client_base_name="ivan",
        plan_config_indexes=[1],
        access_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    germany = _node(db, name="Germany")
    _assign(db, ivan, germany)

    with pytest.raises(HTTPException) as exc:
        enqueue_user_provision(db, user_id=ivan.id, actor_username="admin", confirm_deletions=False)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "access_expired"


def test_enqueue_user_provision_returns_existing_active_task(
    db, patch_sessions, features_on, no_enqueue
):
    ivan = _user(db, username="ivan", client_base_name="ivan", plan_config_indexes=[1])
    germany = _node(db, name="Germany")
    _assign(db, ivan, germany)

    first = enqueue_user_provision(db, user_id=ivan.id, actor_username="admin", confirm_deletions=False)
    second = enqueue_user_provision(db, user_id=ivan.id, actor_username="admin", confirm_deletions=False)
    assert second.id == first.id  # same active task returned
    assert len(no_enqueue) == 1  # only the first enqueue actually submitted


def test_skip_remaining_on_node_after_network_error(db, features_on):
    """Per-node skip is covered by ``_apply_node`` (no ThreadPool / notify side effects)."""
    from app.services.user_provisioning import PlanItem, _apply_node

    ivan = _user(db, username="ivan", client_base_name="ivan", plan_config_indexes=[1, 2, 3])
    germany = _node(db, name="Germany")
    admin = _user(db, username="admin", client_base_name="adminbase", plan_config_indexes=[1])
    admin.role = UserRole.admin
    db.commit()

    items = [
        PlanItem(
            node_id=germany.id,
            node_label="Germany",
            client_name=name,
            vpn_type="wireguard",
            action="create",
        )
        for name in ("ivan", "ivan-2", "ivan-3")
    ]
    calls = []

    def fake_provision_config(session, *, node, client_name, vpn_type, owner, actor, notify=False, **_kwargs):
        calls.append(client_name)
        if client_name == "ivan":
            raise httpx.HTTPError("network down")
        return (type("C", (), {"id": 1})(), None)

    with patch(
        "app.services.user_provisioning.provision_config", side_effect=fake_provision_config
    ):
        results = _apply_node(germany.id, items, db, ivan, admin)

    assert len(results) == 3
    assert results[0]["status"] == "error"
    assert all(r["status"] == "skipped" for r in results[1:])
    assert calls == ["ivan"]
