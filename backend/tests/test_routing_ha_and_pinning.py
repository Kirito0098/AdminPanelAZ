"""Routing HA replication and node pinning for queued routing tasks.

* Toggling a provider on the primary must create/remove the ``AP-*-include-ips.txt``
  file on every replica, otherwise failover routes differently.
* A queued routing task must stay on the node it was enqueued for: an active-node
  switch in another tab must not redirect doall to another server.
* ``/routing/sync`` is long-running (reads all lists, pushes to replicas), so it
  runs as a background task and the HTTP response only carries ``task_id``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.auth import require_admin
from app.database import get_db
from app.routers import routing
from app.services.background_tasks import background_task_service as real_task_service
from app.services.node_sync import provider_sync

ADMIN = SimpleNamespace(username="admin", id=1)


def _node(node_id: int, name: str) -> MagicMock:
    node = MagicMock()
    node.id = node_id
    node.name = name
    node.openvpn_multihome = False
    return node


def _queued_task(task_id: str, task_type: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        task_type=task_type,
        status="queued",
        message="queued",
        output=None,
        error=None,
        progress_percent=0,
        progress_stage=None,
        created_at=None,
        started_at=None,
        finished_at=None,
    )


class _FakeTaskService:
    """Records the queued callable instead of running it in the executor thread."""

    def __init__(self, *, task_type: str = "routing_apply", task_id: str = "task-1", active=None) -> None:
        self.task = _queued_task(task_id, task_type)
        self.active = active
        self.calls: list[tuple[str, object, dict]] = []
        self.task_routing_apply = MagicMock(return_value={"message": "ok", "output": ""})

    def find_active_task(self, task_type: str):
        return self.active

    def enqueue_background_task(self, task_type, task_callable, **kwargs):
        self.calls.append((task_type, task_callable, kwargs))
        return self.task

    def build_accepted_payload(self, task, message):
        return real_task_service.build_accepted_payload(task, message)


def _client(monkeypatch, task_service: _FakeTaskService | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(routing.router)
    app.dependency_overrides[require_admin] = lambda: ADMIN
    app.dependency_overrides[get_db] = lambda: MagicMock()
    if task_service is not None:
        monkeypatch.setattr(routing, "background_task_service", task_service)
    return TestClient(app)


# --- provider toggle replication -------------------------------------------


@pytest.fixture
def ha_toggle(monkeypatch):
    primary = _node(1, "primary")
    down = _node(2, "replica-down")
    up = _node(3, "replica-up")
    primary_adapter = MagicMock(name="primary_adapter")
    up_adapter = MagicMock(name="up_adapter")
    group = MagicMock()

    monkeypatch.setattr(routing, "require_ha_primary_for_config_ops", lambda _db: None)
    monkeypatch.setattr(routing, "get_active_adapter", lambda _db: primary_adapter)
    monkeypatch.setattr(routing, "get_active_node", lambda _db: primary)
    monkeypatch.setattr(routing, "find_sync_group_for_primary", lambda _db, _node_id: group)
    monkeypatch.setattr(routing, "is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr(provider_sync, "is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr(provider_sync, "get_replica_nodes", lambda _db, _group: [down, up])
    monkeypatch.setattr(provider_sync, "finalize_replicate_outcome", MagicMock())

    def adapter_for(node):
        if node is down:
            raise RuntimeError("SSH-туннель к replica-down не поднялся")
        return up_adapter

    monkeypatch.setattr(provider_sync, "get_adapter_for_node", adapter_for)
    return SimpleNamespace(
        primary_adapter=primary_adapter,
        up_adapter=up_adapter,
        down=down,
        up=up,
    )


def test_provider_toggle_replicates_to_replicas_and_reports_failure(monkeypatch, ha_toggle):
    client = _client(monkeypatch)

    resp = client.post(
        "/routing/providers/AP-1-include-ips.txt/enabled",
        json={"enabled": True},
    )

    assert resp.status_code == 200
    ha_toggle.primary_adapter.set_provider_enabled.assert_called_once_with(
        "AP-1-include-ips.txt", True
    )
    ha_toggle.up_adapter.set_provider_enabled.assert_called_once_with(
        "AP-1-include-ips.txt", True
    )
    body = resp.json()
    assert any("replica-down" in warning for warning in body["warnings"])
    assert any("SSH-туннель" in warning for warning in body["warnings"])


def test_provider_toggle_replica_error_reason_is_reported(monkeypatch, ha_toggle):
    monkeypatch.setattr(provider_sync, "get_replica_nodes", lambda _db, _group: [ha_toggle.down])
    client = _client(monkeypatch)

    resp = client.post(
        "/routing/providers/AP-1-include-ips.txt/enabled",
        json={"enabled": False},
    )

    assert resp.status_code == 200
    assert resp.json()["warnings"][0].startswith("HA replica «replica-down»")
    ha_toggle.up_adapter.set_provider_enabled.assert_not_called()


def test_provider_toggle_requires_primary(monkeypatch):
    def forbid(_db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="HA replica")

    monkeypatch.setattr(routing, "require_ha_primary_for_config_ops", forbid)
    client = _client(monkeypatch)

    resp = client.post(
        "/routing/providers/AP-1-include-ips.txt/enabled",
        json={"enabled": True},
    )

    assert resp.status_code == 403


# --- routing apply node pinning --------------------------------------------


def _pin_apply_env(monkeypatch, *, pinned: MagicMock):
    service = _FakeTaskService()
    adapter = MagicMock(name="pinned_adapter")
    used: dict[str, object] = {}

    def adapter_for(node):
        used["node"] = node
        return adapter

    def task_routing_apply(adapter_arg, progress_updater=None, **kwargs):
        used["adapter"] = adapter_arg
        used["hosts"] = kwargs.get("hosts")
        used["multihome"] = kwargs.get("ensure_openvpn_multihome")
        return {"message": "Маршрутизация применена", "output": ""}

    service.task_routing_apply = task_routing_apply
    worker_db = MagicMock()
    worker_db.get.side_effect = lambda _model, node_id: pinned if node_id == pinned.id else None

    monkeypatch.setattr(routing, "background_task_service", service)
    monkeypatch.setattr(routing, "get_active_node", lambda _db: pinned)
    monkeypatch.setattr(routing, "find_sync_group_for_primary", lambda _db, _node_id: None)
    monkeypatch.setattr(routing, "get_active_adapter", MagicMock(name="get_active_adapter"))
    monkeypatch.setattr(routing, "load_node_remote_hosts", lambda _db, _node_id: ["vpn.example.com"])
    monkeypatch.setattr("app.database.SessionLocal", lambda: worker_db)
    monkeypatch.setattr("app.services.node_manager.get_adapter_for_node", adapter_for)
    return service, used, adapter


def test_routing_apply_task_uses_enqueued_node_after_switch(monkeypatch):
    pinned = _node(7, "pinned-primary")
    switched = _node(9, "other-node")
    service, used, adapter = _pin_apply_env(monkeypatch, pinned=pinned)

    task = routing._enqueue_routing_apply_tasks(MagicMock(), created_by_username="admin")
    assert task is service.task
    assert service.calls[0][0] == "routing_apply"

    # Another tab activated a different node after the task was queued.
    monkeypatch.setattr(routing, "get_active_node", lambda _db: switched)
    result = service.calls[0][1](progress_updater=None)

    assert result == {"message": "Маршрутизация применена", "output": ""}
    assert used["node"] is pinned
    assert used["adapter"] is adapter
    assert used["hosts"] == ["vpn.example.com"]
    routing.get_active_adapter.assert_not_called()


def test_routing_apply_task_fails_when_pinned_node_is_gone(monkeypatch):
    pinned = _node(7, "pinned-primary")
    service, used, _adapter = _pin_apply_env(monkeypatch, pinned=pinned)
    service.calls.clear()

    worker_db = MagicMock()
    worker_db.get.return_value = None
    monkeypatch.setattr("app.database.SessionLocal", lambda: worker_db)

    routing._enqueue_routing_apply_tasks(MagicMock(), created_by_username="admin")
    callable_ = service.calls[0][1]

    with pytest.raises(RuntimeError, match="Узел 7 больше не существует"):
        callable_(progress_updater=None)
    assert "node" not in used
    routing.get_active_adapter.assert_not_called()


# --- /routing/sync background task -----------------------------------------


def test_sync_endpoint_queues_task_without_running_it(monkeypatch):
    node = _node(5, "primary")
    get_active_adapter = MagicMock(name="get_active_adapter")
    service = _FakeTaskService(task_type="routing_sync", task_id="sync-task-1")

    monkeypatch.setattr(routing, "require_ha_primary_for_config_ops", lambda _db: None)
    monkeypatch.setattr(routing, "get_active_adapter", get_active_adapter)
    monkeypatch.setattr(routing, "get_active_node", lambda _db: node)
    monkeypatch.setattr(routing, "find_sync_group_for_primary", lambda _db, _node_id: None)
    client = _client(monkeypatch, service)

    resp = client.post("/routing/sync")

    assert resp.status_code == 202
    body = resp.json()
    assert body["task_id"] == "sync-task-1"
    assert body["queued"] is True
    assert body["success"] is True
    assert service.calls[0][0] == "routing_sync"
    assert service.calls[0][1].__name__ == "_callable"
    get_active_adapter.assert_not_called()


def test_sync_task_callable_syncs_providers_on_pinned_node(monkeypatch):
    node = _node(5, "primary")
    adapter = MagicMock(name="pinned_adapter")
    adapter.sync_cidr_providers.return_value = {"restored": [], "sync": []}
    service = _FakeTaskService(task_type="routing_sync", task_id="sync-task-2")
    worker_db = MagicMock()
    worker_db.get.return_value = node

    monkeypatch.setattr(routing, "require_ha_primary_for_config_ops", lambda _db: None)
    monkeypatch.setattr(routing, "get_active_node", lambda _db: node)
    monkeypatch.setattr(routing, "find_sync_group_for_primary", lambda _db, _node_id: None)
    monkeypatch.setattr(routing, "get_active_adapter", MagicMock(name="get_active_adapter"))
    monkeypatch.setattr("app.database.SessionLocal", lambda: worker_db)
    monkeypatch.setattr(
        "app.services.node_manager.get_adapter_for_node", lambda _node: adapter
    )
    client = _client(monkeypatch, service)

    assert client.post("/routing/sync").status_code == 202
    result = service.calls[0][1](progress_updater=None)

    adapter.sync_cidr_providers.assert_called_once_with()
    assert result["success"] is True
    assert "restored" in result["output"]


def test_sync_endpoint_conflicts_with_running_task(monkeypatch):
    service = _FakeTaskService(
        task_type="routing_sync",
        active=SimpleNamespace(id="running-task"),
    )
    get_active_adapter = MagicMock(name="get_active_adapter")
    monkeypatch.setattr(routing, "require_ha_primary_for_config_ops", lambda _db: None)
    monkeypatch.setattr(routing, "get_active_adapter", get_active_adapter)
    monkeypatch.setattr(routing, "get_active_node", lambda _db: _node(5, "primary"))
    client = _client(monkeypatch, service)

    resp = client.post("/routing/sync")

    assert resp.status_code == 409
    assert resp.json()["active_task_id"] == "running-task"
    assert service.calls == []
    get_active_adapter.assert_not_called()


def test_sync_endpoint_requires_primary(monkeypatch):
    def forbid(_db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="HA replica")

    monkeypatch.setattr(routing, "require_ha_primary_for_config_ops", forbid)
    client = _client(monkeypatch, _FakeTaskService(task_type="routing_sync"))

    assert client.post("/routing/sync").status_code == 403
