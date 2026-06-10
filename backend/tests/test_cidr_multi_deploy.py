"""Multi-node CIDR deploy tests (Phase 4)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import Node, NodeStatus
from app.services.cidr.cidr_tasks import enable_memory_backend_for_tests
from app.services.cidr.pipeline.orchestrator import resolve_deploy_targets, run_multi_deploy


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


def _add_remote_node(session, name, node_status=NodeStatus.online, node_id=None):
    node = Node(
        name=name,
        host=f"{name}.example.com",
        port=9100,
        is_local=False,
        status=node_status,
        api_key_hash="hash",
        api_key_encrypted="enc",
    )
    if node_id is not None:
        node.id = node_id
    session.add(node)
    session.commit()
    session.refresh(node)
    return node


def test_resolve_deploy_targets_all_online(deploy_env):
    session = deploy_env["session_factory"]()
    _add_remote_node(session, "remote-a", NodeStatus.online)
    _add_remote_node(session, "remote-b", NodeStatus.offline)

    nodes, skipped = resolve_deploy_targets(session, all_online=True)
    assert len(nodes) == 2  # local + remote-a online
    assert all(n.status == NodeStatus.online for n in nodes)
    assert skipped == []


def test_resolve_deploy_targets_skips_offline(deploy_env):
    session = deploy_env["session_factory"]()
    offline = _add_remote_node(session, "remote-off", NodeStatus.offline)

    nodes, skipped = resolve_deploy_targets(session, target_node_ids=[offline.id])
    assert nodes == []
    assert len(skipped) == 1
    assert skipped[0]["status"] == "skipped"
    assert skipped[0]["node_id"] == offline.id


def test_run_multi_deploy_iterates_online_nodes(deploy_env):
    session = deploy_env["session_factory"]()
    remote = _add_remote_node(session, "remote-ok", NodeStatus.online)

    adapter = MagicMock()
    adapter.sync_cidr_providers.return_value = {"changed": 1}

    with patch("app.services.cidr.pipeline.orchestrator.get_adapter_for_node", return_value=adapter), patch(
        "app.services.cidr.pipeline.orchestrator.run_deploy"
    ) as run_deploy, patch(
        "app.services.cidr.pipeline.orchestrator.compute_artifact_stamp", return_value="abc123"
    ):
        run_deploy.return_value = {"mode": "remote", "pushed": ["aws.txt"], "failed": [], "sync": {"changed": 1}}

        result = run_multi_deploy(
            session,
            target_node_ids=[remote.id],
            sync_after=True,
            apply_after=False,
        )

    assert run_deploy.call_count == 1
    assert result["artifact_stamp"] == "abc123"
    assert result["nodes_deployed"] == 1
    assert len(result["per_node"]) == 1
    assert result["per_node"][0]["status"] == "success"
    assert result["per_node"][0]["node_id"] == remote.id
    assert result["per_node"][0]["pushed_files"] == ["aws.txt"]


def test_run_multi_deploy_offline_does_not_break_others(deploy_env):
    session = deploy_env["session_factory"]()
    online = _add_remote_node(session, "remote-on", NodeStatus.online)
    offline = _add_remote_node(session, "remote-off", NodeStatus.offline)

    adapter = MagicMock()
    with patch("app.services.cidr.pipeline.orchestrator.get_adapter_for_node", return_value=adapter), patch(
        "app.services.cidr.pipeline.orchestrator.run_deploy"
    ) as run_deploy, patch(
        "app.services.cidr.pipeline.orchestrator.compute_artifact_stamp", return_value="stamp1"
    ):
        run_deploy.return_value = {"mode": "remote", "pushed": ["a.txt"], "failed": []}

        result = run_multi_deploy(
            session,
            target_node_ids=[online.id, offline.id],
        )

    assert run_deploy.call_count == 1
    assert result["nodes_deployed"] == 1
    assert result["nodes_skipped"] == 1
    statuses = {entry["node_id"]: entry["status"] for entry in result["per_node"]}
    assert statuses[online.id] == "success"
    assert statuses[offline.id] == "skipped"


def test_deploy_api_multi_node_returns_202(deploy_env):
    client = _client(deploy_env)
    session = deploy_env["session_factory"]()
    remote = _add_remote_node(session, "remote-api", NodeStatus.online)

    with patch("app.routers.cidr_db.run_multi_deploy") as run_multi:
        run_multi.return_value = {
            "success": True,
            "message": "ok",
            "artifact_stamp": "x",
            "per_node": [{"node_id": remote.id, "status": "success", "pushed_files": ["a.txt"], "failed": []}],
            "deploy": {"pushed": ["a.txt"], "failed": []},
            "nodes_deployed": 1,
            "nodes_failed": 0,
            "nodes_skipped": 0,
        }

        resp = client.post(
            "/api/routing/cidr-db/deploy",
            headers=deploy_env["admin_headers"],
            json={"target_node_ids": [remote.id], "sync_after": True},
        )

    assert resp.status_code == 202
    assert resp.json()["task_id"]


def test_deploy_status_includes_per_node(deploy_env):
    from datetime import datetime, timezone

    from app.services.cidr.cidr_tasks import create_cidr_task, update_cidr_task

    per_node = [
        {"node_id": 1, "node_name": "n1", "status": "success", "pushed_files": ["a.txt"], "failed": []},
        {"node_id": 2, "node_name": "n2", "status": "skipped", "pushed_files": [], "failed": [], "error": "offline"},
    ]
    task_id = create_cidr_task("cidr_deploy", "multi deploy")
    update_cidr_task(
        task_id,
        status="completed",
        finished_at=datetime(2026, 6, 10, 14, 0, tzinfo=timezone.utc),
        message="Развёрнуто на 1 узел(ов)",
        result={
            "success": True,
            "artifact_stamp": "deadbeef",
            "per_node": per_node,
            "deploy": {"pushed": ["a.txt"], "failed": []},
            "nodes_deployed": 1,
            "nodes_failed": 0,
            "nodes_skipped": 1,
        },
    )

    client = _client(deploy_env)
    resp = client.get("/api/routing/cidr-db/deploy/status", headers=deploy_env["admin_headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["last_deploy"]["artifact_stamp"] == "deadbeef"
    assert len(data["last_deploy"]["per_node"]) == 2


def test_run_multi_deploy_failure_notifies_admin(deploy_env):
    session = deploy_env["session_factory"]()
    remote = _add_remote_node(session, "remote-fail", NodeStatus.online)

    adapter = MagicMock()
    with patch("app.services.cidr.pipeline.orchestrator.get_adapter_for_node", return_value=adapter), patch(
        "app.services.cidr.pipeline.orchestrator.run_deploy"
    ) as run_deploy, patch(
        "app.services.cidr.pipeline.orchestrator.compute_artifact_stamp", return_value="failstamp"
    ), patch(
        "app.services.cidr.pipeline.orchestrator.maybe_notify_deploy_failed"
    ) as notify_failed:
        run_deploy.return_value = {
            "mode": "remote",
            "pushed": [],
            "failed": [{"file": "aws.txt", "error": "connection refused"}],
        }

        result = run_multi_deploy(
            session,
            target_node_ids=[remote.id],
            triggered_by="manual:admin",
        )

    assert result["success"] is False
    notify_failed.assert_called_once()
    call_args = notify_failed.call_args
    assert call_args[0][0] is session
    assert call_args[0][1]["nodes_failed"] == 1
    assert call_args[1]["triggered_by"] == "manual:admin"
