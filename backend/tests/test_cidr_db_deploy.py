"""CIDR deploy API tests (Phase 3)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.cidr.cidr_tasks import enable_memory_backend_for_tests


@pytest.fixture()
def deploy_env(api_test_env):
    from app.services.cidr.cidr_tasks import _CIDR_TASKS

    enable_memory_backend_for_tests(True)
    _CIDR_TASKS.clear()
    yield api_test_env
    _CIDR_TASKS.clear()
    enable_memory_backend_for_tests(False)


def _client(env):
    return TestClient(env["app"])


def test_deploy_returns_202_and_task_id(deploy_env):
    client = _client(deploy_env)
    with patch("app.routers.cidr_db.get_active_adapter") as get_adapter, patch(
        "app.routers.cidr_db.run_deploy"
    ) as run_deploy:
        adapter = MagicMock()
        get_adapter.return_value = adapter
        run_deploy.return_value = {"mode": "remote", "pushed": ["aws.txt"], "failed": [], "sync": {"changed": 1}}

        resp = client.post(
            "/api/routing/cidr-db/deploy",
            headers=deploy_env["admin_headers"],
            json={"sync_after": True, "apply_after": False},
        )

    assert resp.status_code == 202
    data = resp.json()
    assert data["success"] is True
    assert data["queued"] is True
    assert data["task_id"]


def test_deploy_rejects_viewer(deploy_env):
    client = _client(deploy_env)
    resp = client.post(
        "/api/routing/cidr-db/deploy",
        headers=deploy_env["viewer_headers"],
        json={},
    )
    assert resp.status_code == 403


def test_status_includes_last_deploy(deploy_env):
    from datetime import datetime, timezone

    from app.services.cidr.cidr_tasks import create_cidr_task, update_cidr_task

    task_id = create_cidr_task("cidr_deploy", "test deploy")
    update_cidr_task(
        task_id,
        status="completed",
        finished_at=datetime(2026, 6, 10, 16, 0, tzinfo=timezone.utc),
        message="Развёрнуто файлов: 2",
        result={
            "success": True,
            "deploy": {"pushed": ["a.txt", "b.txt"], "failed": []},
            "target_node_id": None,
        },
    )

    client = _client(deploy_env)
    resp = client.get("/api/routing/cidr-db/status", headers=deploy_env["admin_headers"])
    assert resp.status_code == 200
    last_deploy = resp.json().get("last_deploy")
    assert last_deploy is not None
    assert last_deploy["pushed_count"] == 2
    assert last_deploy["failed_count"] == 0
    assert last_deploy["status"] == "completed"


def test_status_includes_compile_artifacts(deploy_env, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.cidr.pipeline.deploy.LIST_DIR", str(tmp_path))
    (tmp_path / "aws.txt").write_text("10.0.0.0/8\n", encoding="utf-8")

    client = _client(deploy_env)
    resp = client.get("/api/routing/cidr-db/status", headers=deploy_env["admin_headers"])
    assert resp.status_code == 200
    artifacts = resp.json().get("compile_artifacts")
    assert artifacts is not None
    assert artifacts["aws.txt"]["cidr_count"] == 1
    assert artifacts["aws.txt"]["exists"] is True


def test_status_includes_last_compile_at(deploy_env):
    from datetime import datetime, timezone

    from app.services.cidr.cidr_tasks import create_cidr_task, update_cidr_task

    task_id = create_cidr_task("cidr_generate_from_db", "test compile")
    update_cidr_task(
        task_id,
        status="completed",
        finished_at=datetime(2026, 6, 10, 15, 30, tzinfo=timezone.utc),
        message="Сгенерировано 3 файла",
        result={
            "success": True,
            "updated": ["aws.txt", "gcp.txt", "azure.txt"],
            "artifact_stamp": "abc12345",
        },
    )

    client = _client(deploy_env)
    resp = client.get("/api/routing/cidr-db/status", headers=deploy_env["admin_headers"])
    assert resp.status_code == 200
    last_compile = resp.json().get("last_compile_at")
    assert last_compile is not None
    assert last_compile["files_updated"] == 3
    assert last_compile["status"] == "completed"
    assert last_compile["artifact_stamp"] == "abc12345"


def test_deploy_logs_action(deploy_env):
    from app.models import UserActionLog

    client = _client(deploy_env)
    session = deploy_env["session_factory"]()

    with patch("app.routers.cidr_db.run_multi_deploy") as run_multi:
        run_multi.return_value = {
            "success": True,
            "message": "ok",
            "per_node": [],
            "deploy": {"pushed": [], "failed": []},
            "nodes_deployed": 1,
            "nodes_failed": 0,
            "nodes_skipped": 0,
        }
        resp = client.post(
            "/api/routing/cidr-db/deploy",
            headers=deploy_env["admin_headers"],
            json={"all_online": True},
        )

    assert resp.status_code == 202
    log = (
        session.query(UserActionLog)
        .filter(UserActionLog.action == "settings_cidr_deploy")
        .order_by(UserActionLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.details == "all_online"
    assert log.username == "api_admin"
