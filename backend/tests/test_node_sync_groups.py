"""NodeSyncGroup CRUD API tests."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from tests.conftest import run_async


@pytest.fixture()
def sync_nodes(api_test_env):
    session = api_test_env["session_factory"]()
    primary = Node(
        name="primary",
        host="10.0.0.1",
        port=9100,
        status=NodeStatus.online,
        node_metadata=json.dumps({"antizapret_version": "v1.0.0"}),
    )
    replica = Node(
        name="replica",
        host="10.0.0.2",
        port=9100,
        status=NodeStatus.online,
        node_metadata=json.dumps({"antizapret_version": "v1.0.0"}),
    )
    session.add_all([primary, replica])
    session.commit()
    api_test_env["primary_id"] = primary.id
    api_test_env["replica_id"] = replica.id
    api_test_env["local_node_id"] = api_test_env["node"].id
    session.close()
    yield api_test_env
    session = api_test_env["session_factory"]()
    session.query(NodeSyncGroup).delete()
    session.commit()
    session.close()


def test_create_sync_group(sync_nodes):
    env = sync_nodes
    app = env["app"]
    headers = env["admin_headers"]

    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/nodes/sync-groups",
                headers=headers,
                json={
                    "name": "HA vpn",
                    "shared_domain": "vpn.example.com",
                    "primary_node_id": env["primary_id"],
                    "replica_node_ids": [env["replica_id"]],
                },
            )
        return response

    response = run_async(_run())
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "HA vpn"
    assert data["shared_domain"] == "vpn.example.com"
    assert data["sync_status"] == "unknown"
    assert env["replica_id"] in data["replica_node_ids"]


def test_reject_duplicate_node_in_group(sync_nodes):
    env = sync_nodes
    app = env["app"]
    headers = env["admin_headers"]

    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/api/nodes/sync-groups",
                headers=headers,
                json={
                    "name": "Group A",
                    "shared_domain": "vpn.example.com",
                    "primary_node_id": env["primary_id"],
                    "replica_node_ids": [env["replica_id"]],
                },
            )
            second = await client.post(
                "/api/nodes/sync-groups",
                headers=headers,
                json={
                    "name": "Group B",
                    "shared_domain": "vpn2.example.com",
                    "primary_node_id": env["local_node_id"],
                    "replica_node_ids": [env["replica_id"]],
                },
            )
        return first, second

    first, second = run_async(_run())
    assert first.status_code == 201
    assert second.status_code == 422


def test_list_and_delete_sync_group(sync_nodes):
    env = sync_nodes
    app = env["app"]
    headers = env["admin_headers"]

    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/nodes/sync-groups",
                headers=headers,
                json={
                    "name": "HA",
                    "shared_domain": "vpn.example.com",
                    "primary_node_id": env["primary_id"],
                    "replica_node_ids": [env["replica_id"]],
                },
            )
            group_id = created.json()["id"]
            listed = await client.get("/api/nodes/sync-groups", headers=headers)
            deleted = await client.delete(f"/api/nodes/sync-groups/{group_id}", headers=headers)
            after = await client.get("/api/nodes/sync-groups", headers=headers)
        return created, listed, deleted, after

    created, listed, deleted, after = run_async(_run())
    assert created.status_code == 201
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert deleted.status_code == 200
    assert "расформирована" in deleted.json()["message"]
    assert "сохранены" in deleted.json()["message"]
    assert after.json() == []
