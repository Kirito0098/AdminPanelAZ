"""Tests for rolling node update queue."""

import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models import Node, NodeStatus


def _client(env):
    return TestClient(env["app"])


def test_node_update_roll_sequential(api_test_env):
    env = api_test_env
    session = env["session_factory"]()
    try:
        remote = Node(
            name="remote-roll",
            host="10.0.0.9",
            port=9100,
            api_key_hash="hash",
            api_key_encrypted="enc",
            is_local=False,
            status=NodeStatus.online,
        )
        session.add(remote)
        session.commit()
        session.refresh(remote)
        remote_id = remote.id
    finally:
        session.close()

    calls: list[int] = []

    def _fake_update(node_id: int):
        calls.append(node_id)
        return {
            "node_id": node_id,
            "node_name": "remote-roll" if node_id == remote_id else "local",
            "ok": True,
            "message": "ok",
            "restarting": False,
            "errors": [],
        }

    with patch("app.services.node_update_roll._update_single_node", side_effect=_fake_update):
        response = _client(env).post(
            "/api/nodes/update-roll",
            json={"node_ids": [env["node"].id, remote_id]},
            headers=env["admin_headers"],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["queued"] is True
    task_id = body["task_id"]

    deadline = time.time() + 10
    status = None
    while time.time() < deadline:
        status = _client(env).get(f"/api/tasks/{task_id}", headers=env["admin_headers"]).json()
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.2)

    assert status is not None
    assert status["status"] == "completed"
    assert status["task_type"] == "node_update_roll"
    assert calls == [env["node"].id, remote_id]
