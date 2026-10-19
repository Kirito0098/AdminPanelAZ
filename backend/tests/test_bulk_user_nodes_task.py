"""Stage 4 Task 3–5: HTTP-маршруты и фоновая задача ``bulk_user_nodes``.

TDD: маршруты закрыты гейтом ``user_provisioning`` и правами админа,
удаление требует подтверждения именем сервера, а фоновая задача может быть
только одна (``subject_key="bulk_nodes"``).
"""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user_access_token
from app.database import Base, get_db
from app.models import (
    BackgroundTask,
    Node,
    NodeStatus,
    User,
    UserRole,
    UserNodeAssignment,
)
from app.routers import users as users_router
from app.schemas import BulkNodesRequest, BulkNodesScope
from app.services.bulk_user_nodes import (
    BulkUserNodeResult,
    enqueue_bulk_user_nodes,
    run_bulk_user_nodes_task,
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


@pytest.fixture(autouse=True)
def _patch_sessions(monkeypatch, db):
    """Фоновые задачи не должны ходить в боевую БД панели."""
    TestSessionLocal = sessionmaker(bind=db.bind)
    monkeypatch.setattr("app.services.background_tasks.SessionLocal", lambda: TestSessionLocal())
    monkeypatch.setattr("app.services.bulk_user_nodes.SessionLocal", lambda: TestSessionLocal())


@pytest.fixture()
def submitted(monkeypatch):
    """Фоновые задачи не запускаются в потоках — только записываются."""
    calls = []

    def fake_submit(fn, *args, **kwargs):
        calls.append((fn, args, kwargs))

    monkeypatch.setattr("app.services.bulk_user_nodes._submit_in_current_context", fake_submit)
    return calls


@pytest.fixture()
def client(db, monkeypatch, submitted):
    TestSessionLocal = sessionmaker(bind=db.bind)
    monkeypatch.setattr("app.services.background_tasks.SessionLocal", lambda: TestSessionLocal())
    monkeypatch.setattr("app.services.bulk_user_nodes.SessionLocal", lambda: TestSessionLocal())

    class Features:
        def __init__(self, enabled=True):
            self.enabled = enabled

        def is_enabled(self, key):
            return self.enabled

    monkeypatch.setattr("app.routers.users.get_feature_service", lambda: Features())
    monkeypatch.setattr("app.services.bulk_user_nodes.get_feature_service", lambda: Features())

    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


@pytest.fixture()
def admin(db):
    user = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def plain_user(db):
    user = User(username="ivan", password_hash="x", role=UserRole.user, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def germany(db):
    node = Node(
        name="Germany", host="127.0.0.1", port=9100, api_key_hash="h", api_key_encrypted="e",
        status=NodeStatus.online, is_local=True, node_kind="vpn", node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@pytest.fixture()
def finland(db):
    node = Node(
        name="Finland", host="127.0.0.2", port=9100, api_key_hash="h", api_key_encrypted="e",
        status=NodeStatus.online, is_local=True, node_kind="vpn", node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _planned_user(db, username="ivan", base="ivan"):
    user = User(
        username=username, password_hash="x", role=UserRole.user, client_base_name=base,
        plan_config_indexes=json.dumps([1]), desired_protocols=json.dumps(["wireguard"]),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth(user):
    return {"Authorization": f"Bearer {create_user_access_token(user)}"}


@pytest.fixture()
def finished_bulk_task(db):
    task = BackgroundTask(
        id="done-task",
        task_type="bulk_user_nodes",
        status="completed",
        output=json.dumps(
            {
                "action": "add",
                "node_label": "Finland",
                "ok_count": 1,
                "failed_count": 0,
                "results": [{"user_id": 1, "username": "ivan", "status": "ok"}],
            },
            ensure_ascii=False,
        ),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


# --- Task 3: маршруты ----------------------------------------------------


def test_preview_requires_admin(client, plain_user):
    response = client.post(
        "/api/users/bulk/nodes/preview",
        json={"action": "add", "node_id": 1, "scope": {"mode": "all"}},
        headers=_auth(plain_user),
    )
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def test_preview_requires_provisioning_toggle(client, db, admin, germany, monkeypatch):
    class Features:
        def is_enabled(self, key):
            return key != "user_provisioning"

    monkeypatch.setattr("app.routers.users.get_feature_service", lambda: Features())
    response = client.post(
        "/api/users/bulk/nodes/preview",
        json={"action": "add", "node_id": germany.id, "scope": {"mode": "all"}},
        headers=_auth(admin),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_preview_returns_counts(client, db, admin, germany):
    ivan = _planned_user(db)
    db.add(UserNodeAssignment(user_id=ivan.id, node_id=germany.id))
    db.commit()

    response = client.post(
        "/api/users/bulk/nodes/preview",
        json={"action": "add", "node_id": germany.id, "scope": {"mode": "all"}},
        headers=_auth(admin),
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["node_label"] == "Germany"
    assert body["action"] == "add"
    assert isinstance(body["affected"], list)
    assert "skipped" in body


def test_start_requires_confirm_node_name_for_remove(client, db, admin, germany):
    response = client.post(
        "/api/users/bulk/nodes",
        json={"action": "remove", "node_id": germany.id, "scope": {"mode": "all"}},
        headers=_auth(admin),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "имя" in str(response.json()).lower()


def test_start_wrong_confirm_name(client, db, admin, germany):
    response = client.post(
        "/api/users/bulk/nodes",
        json={
            "action": "remove",
            "node_id": germany.id,
            "scope": {"mode": "all"},
            "confirm_node_name": "WRONG",
        },
        headers=_auth(admin),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_start_409_when_bulk_already_running(client, db, admin, finland, monkeypatch):
    monkeypatch.setattr(
        "app.services.bulk_user_nodes.background_task_service.find_active_task",
        lambda task_type, subject_key=None: (
            SimpleNamespace(id="busy")
            if task_type == "bulk_user_nodes" and subject_key == "bulk_nodes"
            else None
        ),
    )
    response = client.post(
        "/api/users/bulk/nodes",
        json={"action": "add", "node_id": finland.id, "scope": {"mode": "all"}},
        headers=_auth(admin),
    )
    assert response.status_code == status.HTTP_409_CONFLICT


def test_start_returns_task_id(client, db, admin, finland, submitted):
    ivan = _planned_user(db)
    response = client.post(
        "/api/users/bulk/nodes",
        json={"action": "add", "node_id": finland.id, "scope": {"mode": "all"}},
        headers=_auth(admin),
    )
    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    body = response.json()
    assert body["task_id"]
    row = db.get(BackgroundTask, body["task_id"])
    assert row.task_type == "bulk_user_nodes"
    assert row.subject_key == "bulk_nodes"
    assert len(submitted) == 1


# --- Task 5: фоновая задача ---------------------------------------------


def test_enqueue_sets_subject_key_bulk_nodes(db, admin, finland, submitted):
    _planned_user(db)
    task = enqueue_bulk_user_nodes(
        db,
        body=BulkNodesRequest(
            action="add", node_id=finland.id, scope=BulkNodesScope(mode="all")
        ),
        actor=admin,
    )
    row = db.get(BackgroundTask, task.id)
    assert row.task_type == "bulk_user_nodes"
    assert row.subject_key == "bulk_nodes"


def test_second_enqueue_409(db, admin, finland, submitted, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        "app.services.bulk_user_nodes.background_task_service.find_active_task",
        lambda *a, **k: SimpleNamespace(id="x"),
    )
    with pytest.raises(HTTPException) as exc:
        enqueue_bulk_user_nodes(
            db,
            body=BulkNodesRequest(
                action="add", node_id=finland.id, scope=BulkNodesScope(mode="all")
            ),
            actor=admin,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "bulk_nodes_running"


def test_run_processes_users_sequentially(db, monkeypatch, admin, finland):
    users = [
        _planned_user(db, username=f"user{index}", base=f"user{index}") for index in range(3)
    ]
    order = []

    def fake_apply(**kwargs):
        order.append(kwargs["user"].id)
        return BulkUserNodeResult(
            user_id=kwargs["user"].id,
            username=kwargs["user"].username,
            status="ok",
            skip_reason=None,
            created=1,
            deleted=0,
            error=None,
        )

    monkeypatch.setattr("app.services.bulk_user_nodes.apply_bulk_user_node", fake_apply)

    out = run_bulk_user_nodes_task(
        "tid",
        {
            "action": "add",
            "node_id": finland.id,
            "to_node_id": None,
            "user_ids": [user.id for user in users],
            "notify_telegram": False,
            "note": None,
            "actor_username": admin.username,
        },
    )
    assert order == [user.id for user in users]
    assert out["ok_count"] == 3
    assert out["failed_count"] == 0


def test_run_reports_progress_format(db, monkeypatch, admin, finland):
    users = [
        _planned_user(db, username=f"user{index}", base=f"user{index}") for index in range(2)
    ]
    stages = []

    def fake_apply(**kwargs):
        return BulkUserNodeResult(
            user_id=kwargs["user"].id,
            username=kwargs["user"].username,
            status="ok",
            skip_reason=None,
            created=1,
            deleted=0,
            error=None,
        )

    monkeypatch.setattr("app.services.bulk_user_nodes.apply_bulk_user_node", fake_apply)
    monkeypatch.setattr(
        "app.services.bulk_user_nodes.background_task_service.update_background_task",
        lambda task_id, **fields: stages.append(fields.get("progress_stage")),
    )

    run_bulk_user_nodes_task(
        "tid",
        {
            "action": "add",
            "node_id": finland.id,
            "to_node_id": None,
            "user_ids": [user.id for user in users],
            "notify_telegram": False,
            "note": None,
            "actor_username": admin.username,
        },
    )
    assert stages[0] == "Finland: 0 / 2 пользователей"


def test_run_output_contains_report(db, monkeypatch, admin, finland):
    user = _planned_user(db)
    monkeypatch.setattr(
        "app.services.bulk_user_nodes.apply_bulk_user_node",
        lambda **kwargs: BulkUserNodeResult(
            user_id=kwargs["user"].id,
            username=kwargs["user"].username,
            status="failed",
            skip_reason=None,
            created=0,
            deleted=0,
            error="agent down",
        ),
    )
    out = run_bulk_user_nodes_task(
        "tid",
        {
            "action": "add",
            "node_id": finland.id,
            "to_node_id": None,
            "user_ids": [user.id],
            "notify_telegram": False,
            "note": None,
            "actor_username": admin.username,
        },
    )
    report = json.loads(out["output"])
    assert report["action"] == "add"
    assert report["node_label"] == "Finland"
    assert report["failed_count"] == 1
    assert report["results"][0]["user_id"] == user.id
    assert report["results"][0]["error"] == "agent down"


# --- Task 8: уведомления, сводка админу, отчёт ----------------------------


def test_task_calls_notify_only_for_ok_users(db, monkeypatch, admin, finland):
    ok_user = _planned_user(db, username="ok", base="ok")
    bad_user = _planned_user(db, username="bad", base="bad")

    def fake_apply(**kwargs):
        good = kwargs["user"].id == ok_user.id
        return BulkUserNodeResult(
            user_id=kwargs["user"].id,
            username=kwargs["user"].username,
            status="ok" if good else "failed",
            skip_reason=None,
            created=1 if good else 0,
            deleted=0,
            error=None if good else "boom",
        )

    calls = []
    monkeypatch.setattr("app.services.bulk_user_nodes.apply_bulk_user_node", fake_apply)
    monkeypatch.setattr(
        "app.services.bulk_user_nodes.maybe_notify_after_user",
        lambda **k: calls.append(k["user"].id) or "sent",
    )

    run_bulk_user_nodes_task(
        "tid",
        {
            "action": "add",
            "node_id": finland.id,
            "to_node_id": None,
            "user_ids": [ok_user.id, bad_user.id],
            "notify_telegram": True,
            "note": None,
            "actor_username": admin.username,
        },
    )
    assert calls == [ok_user.id]


def test_task_counts_notify_statuses(db, monkeypatch, admin, finland):
    user = _planned_user(db)
    monkeypatch.setattr(
        "app.services.bulk_user_nodes.apply_bulk_user_node",
        lambda **kwargs: BulkUserNodeResult(
            user_id=kwargs["user"].id,
            username=kwargs["user"].username,
            status="ok",
            skip_reason=None,
            created=1,
            deleted=0,
            error=None,
        ),
    )
    monkeypatch.setattr(
        "app.services.bulk_user_nodes.maybe_notify_after_user",
        lambda **k: "no_telegram",
    )
    out = run_bulk_user_nodes_task(
        "tid",
        {
            "action": "add",
            "node_id": finland.id,
            "to_node_id": None,
            "user_ids": [user.id],
            "notify_telegram": True,
            "note": None,
            "actor_username": admin.username,
        },
    )
    report = json.loads(out["output"])
    assert report["notify"]["no_telegram"] == 1
    assert report["notify"]["sent"] == 0


def test_task_notify_disabled_counts_all(db, monkeypatch, admin, finland):
    user = _planned_user(db)
    out = run_bulk_user_nodes_task(
        "tid",
        {
            "action": "add",
            "node_id": finland.id,
            "to_node_id": None,
            "user_ids": [user.id],
            "notify_telegram": False,
            "note": None,
            "actor_username": admin.username,
        },
    )
    report = json.loads(out["output"])
    assert report["notify"]["disabled"] == 1


def test_admin_notify_once(db, monkeypatch, admin, finland):
    user = _planned_user(db)
    monkeypatch.setattr(
        "app.services.bulk_user_nodes.apply_bulk_user_node",
        lambda **kwargs: BulkUserNodeResult(
            user_id=kwargs["user"].id,
            username=kwargs["user"].username,
            status="ok",
            skip_reason=None,
            created=1,
            deleted=0,
            error=None,
        ),
    )
    sent = []
    monkeypatch.setattr(
        "app.services.bulk_user_nodes.admin_notify_service.send",
        lambda *a, **k: sent.append(k.get("target_name")),
    )
    run_bulk_user_nodes_task(
        "tid",
        {
            "action": "add",
            "node_id": finland.id,
            "to_node_id": None,
            "user_ids": [user.id],
            "notify_telegram": False,
            "note": None,
            "actor_username": admin.username,
        },
    )
    assert len(sent) == 1
    assert "Finland" in str(sent[0])


def test_report_endpoint_returns_json(client, db, admin, finished_bulk_task):
    response = client.get(
        f"/api/users/bulk/nodes/tasks/{finished_bulk_task.id}/report",
        headers=_auth(admin),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers.get("content-disposition", "")
    body = response.json()
    assert "results" in body


def test_report_endpoint_404_for_other_task(client, db, admin):
    other = BackgroundTask(id="other-task", task_type="user_provision", status="completed")
    db.add(other)
    db.commit()
    response = client.get(
        "/api/users/bulk/nodes/tasks/other-task/report",
        headers=_auth(admin),
    )
    assert response.status_code == 404


def test_report_endpoint_409_while_running(client, db, admin):
    running = BackgroundTask(id="running-task", task_type="bulk_user_nodes", status="running")
    db.add(running)
    db.commit()
    response = client.get(
        "/api/users/bulk/nodes/tasks/running-task/report",
        headers=_auth(admin),
    )
    assert response.status_code == 409
