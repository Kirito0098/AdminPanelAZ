"""Tests for BackgroundTaskService (ported from AdminAntizapret)."""

import subprocess
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.database import Base, get_db
from app.main import app
from app.models import BackgroundTask, Node, NodeStatus, User, UserRole
from app.services.background_tasks import BackgroundTaskService, background_task_service


class FakeExecutor:
    def __init__(self):
        self.submissions: list[tuple[object, tuple[object, ...]]] = []

    def submit(self, fn, *args):
        self.submissions.append((fn, args))
        return None


@pytest.fixture
def bg_service():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    service = BackgroundTaskService()

    original_session_local = None

    def _session_local():
        return TestingSessionLocal()

    with patch("app.services.background_tasks.SessionLocal", TestingSessionLocal):
        yield service, TestingSessionLocal


def test_commit_with_retry_succeeds_after_transient_lock(bg_service):
    service, SessionLocal = bg_service
    db = SessionLocal()
    task = BackgroundTask(id="retry-task", task_type="demo", status="queued", message="old")
    db.add(task)
    db.commit()
    db.close()

    attempts = {"count": 0}

    def flaky_session_local():
        session = SessionLocal()
        original_commit = session.commit

        def patched_commit():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise OperationalError("commit", {}, Exception("database is locked"))
            original_commit()

        session.commit = patched_commit  # type: ignore[method-assign]
        return session

    with patch("app.services.background_tasks.SessionLocal", flaky_session_local):
        with patch("app.services.background_tasks.time.sleep"):
            service.update_background_task("retry-task", message="new")

    db = SessionLocal()
    saved = db.get(BackgroundTask, "retry-task")
    assert saved is not None
    assert saved.message == "new"
    assert attempts["count"] == 3
    db.close()


def test_commit_with_retry_raises_after_max_attempts(bg_service):
    service, SessionLocal = bg_service
    db = SessionLocal()
    task = BackgroundTask(id="fail-task", task_type="demo", status="queued")
    db.add(task)

    def always_locked():
        raise OperationalError("commit", {}, Exception("database is locked"))

    with patch.object(db, "commit", side_effect=always_locked):
        with pytest.raises(OperationalError, match="database is locked"):
            service._commit_with_retry(db)

    db.close()


def test_commit_with_retry_does_not_retry_other_operational_errors(bg_service):
    service, SessionLocal = bg_service
    db = SessionLocal()
    task = BackgroundTask(id="other-error", task_type="demo", status="queued")
    db.add(task)

    attempts = {"count": 0}

    def other_error():
        attempts["count"] += 1
        raise OperationalError("commit", {}, Exception("disk I/O error"))

    with patch.object(db, "commit", side_effect=other_error):
        with pytest.raises(OperationalError, match="disk I/O error"):
            service._commit_with_retry(db)

    assert attempts["count"] == 1
    db.close()


def test_enqueue_background_task_creates_record_and_submits_executor(bg_service):
    service, SessionLocal = bg_service
    executor = FakeExecutor()

    with patch("app.services.background_tasks._EXECUTOR", executor):
        task = service.enqueue_background_task(
            task_type="demo",
            task_callable=lambda progress_updater=None: {"message": "ok", "output": "done"},
            created_by_username="admin",
            queued_message="queued",
        )

    assert task.status == "queued"
    assert task.created_by_username == "admin"
    assert len(executor.submissions) == 1
    submitted_fn, submitted_args = executor.submissions[0]
    assert submitted_fn == service.run_background_task
    assert submitted_args[0] == task.id


def test_run_background_task_marks_completed_and_trims_output(bg_service):
    service, SessionLocal = bg_service
    db = SessionLocal()
    task = BackgroundTask(id="task-1", task_type="demo", status="queued")
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    service.run_background_task(
        task_id,
        lambda progress_updater=None: {"message": "completed", "output": "x" * 60000},
    )

    db = SessionLocal()
    updated = db.get(BackgroundTask, task_id)
    assert updated is not None
    assert updated.status == "completed"
    assert updated.message == "completed"
    assert updated.error is None
    assert "...[truncated]" in (updated.output or "")
    db.close()


def test_run_checked_command_raises_runtime_error_on_nonzero_exit(bg_service):
    service, _ = bg_service
    completed = subprocess.CompletedProcess(
        args=["test"],
        returncode=7,
        stdout="",
        stderr="boom",
    )
    with patch("app.services.background_tasks.subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="кодом 7"):
            service.run_checked_command(["test"])


def test_task_run_doall_runs_recreate_profiles_after_doall(bg_service):
    service, _ = bg_service
    adapter = MagicMock()
    adapter.apply_config_changes.return_value = "doall-out"
    adapter.recreate_profiles.return_value = "recreate-out"

    result = service.task_run_doall(adapter)

    assert "пересоздание" in result["message"]
    adapter.apply_config_changes.assert_called_once()
    adapter.recreate_profiles.assert_called_once()
    assert "doall-out" in result["output"]
    assert "recreate-out" in result["output"]


@pytest.fixture
def api_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    admin = User(
        username="admin",
        password_hash=get_password_hash("secret"),
        role=UserRole.admin,
    )
    db.add(admin)
    db.add(Node(name="local", host="127.0.0.1", port=9100, status=NodeStatus.online, is_local=True))
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with patch("app.services.background_tasks.SessionLocal", TestingSessionLocal):
        with TestClient(app) as client:
            login = client.post("/api/auth/login/json", json={"username": "admin", "password": "secret"})
            token = login.json()["access_token"]
            client.headers.update({"Authorization": f"Bearer {token}"})
            yield client, TestingSessionLocal

    app.dependency_overrides.clear()


def test_get_task_status_endpoint(api_client):
    client, SessionLocal = api_client
    db = SessionLocal()
    task = BackgroundTask(
        id="abc123",
        task_type="run_doall",
        status="running",
        message="working",
        progress_percent=42,
        progress_stage="doall",
    )
    db.add(task)
    db.commit()
    db.close()

    response = client.get("/api/tasks/abc123")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["task_id"] == "abc123"
    assert data["progress_percent"] == 42


def test_routing_apply_returns_202_with_task_id(api_client):
    client, _ = api_client
    adapter = MagicMock()

    with patch("app.routers.routing.get_active_adapter", return_value=adapter):
        with patch.object(background_task_service, "enqueue_background_task") as enqueue_mock:
            fake_task = BackgroundTask(id="task-apply", task_type="routing_apply", status="queued")
            enqueue_mock.return_value = fake_task
            response = client.post("/api/routing/apply")

    assert response.status_code == 202
    data = response.json()
    assert data["task_id"] == "task-apply"
    assert data["queued"] is True
