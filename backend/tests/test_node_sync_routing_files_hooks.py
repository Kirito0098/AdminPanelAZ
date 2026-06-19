"""Integration tests for HA route file auto-sync hooks (routing PUT /files/{file_key})."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import AppSetting, Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.cidr.constants import ROUTE_CONFIG_FILES
from app.services.node_sync.groups import serialize_replica_node_ids


def _set_active_node(session_factory, node_id: int) -> None:
    db = session_factory()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == "active_node_id").first()
        if row:
            row.value = str(node_id)
        else:
            db.add(AppSetting(key="active_node_id", value=str(node_id)))
        db.commit()
    finally:
        db.close()


def _config_adapter():
    store: dict[str, str] = {}
    adapter = MagicMock()

    def _read(fname: str) -> str:
        return store.get(fname, "")

    def _write(fname: str, content: str) -> None:
        store[fname] = content

    adapter.read_config_file.side_effect = _read
    adapter.write_config_file.side_effect = _write
    adapter.apply_config_changes.return_value = "doall ok"
    return adapter, store


def _route_adapter():
    store: dict[str, str] = {}
    adapter = MagicMock()

    def _write_route(file_key: str, content: str) -> dict:
        fname = ROUTE_CONFIG_FILES[file_key]
        store[fname] = content
        return {"file_key": file_key, "filename": fname, "line_count": content.count("\n") + (1 if content else 0)}

    adapter.write_route_file.side_effect = _write_route
    return adapter, store


@pytest.fixture()
def ha_routing_files_env(api_test_env):
    session_factory = api_test_env["session_factory"]
    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica = Node(name="replica-routing-files", host="10.0.0.31", port=9100, status=NodeStatus.online)
    db.add(replica)
    db.commit()
    db.refresh(replica)

    group = NodeSyncGroup(
        name="HA routing files",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    db.add(group)
    db.commit()

    primary_id = primary.id
    replica_id = replica.id
    group_id = group.id
    db.close()

    _set_active_node(session_factory, primary_id)
    yield {
        **api_test_env,
        "primary_id": primary_id,
        "replica_id": replica_id,
        "group_id": group_id,
        "session_factory": session_factory,
    }


def _adapter_for_node(primary_id, primary_adapter, replica_id, replica_adapter):
    def resolve(node):
        if node.id == replica_id:
            return replica_adapter
        if node.id == primary_id:
            return primary_adapter
        return MagicMock()

    return resolve


def test_routing_put_route_file_replicates_to_replica(ha_routing_files_env):
    client = TestClient(ha_routing_files_env["app"])
    primary_adapter, primary_store = _route_adapter()
    replica_adapter, replica_store = _config_adapter()
    adapter_for_node = _adapter_for_node(
        ha_routing_files_env["primary_id"],
        primary_adapter,
        ha_routing_files_env["replica_id"],
        replica_adapter,
    )

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch("app.services.edit_files_transfer.get_adapter_for_node", side_effect=adapter_for_node),
    ):
        response = client.put(
            "/api/routing/files/include_ips",
            headers=ha_routing_files_env["admin_headers"],
            json={"content": "10.0.0.0/8\n"},
        )

    assert response.status_code == 200
    assert primary_store["include-ips.txt"] == "10.0.0.0/8\n"
    assert replica_store["include-ips.txt"] == "10.0.0.0/8\n"
    replica_adapter.apply_config_changes.assert_not_called()


def test_routing_put_route_file_skipped_in_manual_full(ha_routing_files_env):
    session_factory = ha_routing_files_env["session_factory"]
    db = session_factory()
    group = db.query(NodeSyncGroup).filter_by(id=ha_routing_files_env["group_id"]).one()
    group.sync_mode = "manual_full"
    db.commit()
    db.close()

    client = TestClient(ha_routing_files_env["app"])
    primary_adapter, primary_store = _route_adapter()
    replica_adapter, replica_store = _config_adapter()
    adapter_for_node = _adapter_for_node(
        ha_routing_files_env["primary_id"],
        primary_adapter,
        ha_routing_files_env["replica_id"],
        replica_adapter,
    )

    with (
        patch("app.routers.routing.get_active_adapter", return_value=primary_adapter),
        patch("app.services.edit_files_transfer.get_adapter_for_node", side_effect=adapter_for_node),
    ):
        response = client.put(
            "/api/routing/files/include_ips",
            headers=ha_routing_files_env["admin_headers"],
            json={"content": "192.0.2.0/24\n"},
        )

    assert response.status_code == 200
    assert primary_store["include-ips.txt"] == "192.0.2.0/24\n"
    assert replica_store == {}
    replica_adapter.write_config_file.assert_not_called()
