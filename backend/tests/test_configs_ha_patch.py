"""HA auto-sync hooks for bulk ops and config PATCH (step A.3)."""

from __future__ import annotations

from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import AppSetting, Node, NodeStatus, NodeSyncGroup, OpenVpnAccessPolicy, SyncStatus, User, VpnConfig, VpnType
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


def _immediate_submit(fn, *args, **kwargs):
    future: Future = Future()
    try:
        future.set_result(fn(*args, **kwargs))
    except Exception as exc:
        future.set_exception(exc)
    return future


def _ovpn_adapter():
    banned: set[str] = set()
    adapter = MagicMock()

    def _read(name: str) -> str:
        if name == "banned_clients":
            return "\n".join(sorted(banned)) + ("\n" if banned else "")
        return ""

    def _write(name: str, content: str) -> None:
        if name == "banned_clients":
            banned.clear()
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    banned.add(line)

    adapter.read_config_file.side_effect = _read
    adapter.write_config_file.side_effect = _write
    adapter.ensure_openvpn_ban_check.return_value = None
    adapter.add_openvpn_client.return_value = None
    return adapter, banned


@pytest.fixture()
def ha_bulk_env(api_test_env):
    session_factory = api_test_env["session_factory"]
    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica = Node(name="replica-bulk", host="10.0.0.20", port=9100, status=NodeStatus.online)
    admin = db.query(User).filter(User.username == "api_admin").first()
    db.add(replica)
    db.commit()
    db.refresh(replica)

    group = NodeSyncGroup(
        name="HA bulk",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    db.add(group)
    db.commit()

    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="bulk-alice",
        vpn_type=VpnType.openvpn,
        owner_id=admin.id,
        sync_group_id=group.id,
    )
    db.add(primary_config)
    db.commit()
    db.refresh(primary_config)

    shadow = VpnConfig(
        node_id=replica.id,
        client_name="bulk-alice",
        vpn_type=VpnType.openvpn,
        owner_id=admin.id,
        sync_group_id=group.id,
        ha_primary_config_id=primary_config.id,
    )
    db.add(shadow)
    db.commit()

    primary_id = primary.id
    replica_id = replica.id
    config_id = primary_config.id
    db.close()

    _set_active_node(session_factory, primary_id)
    yield {
        **api_test_env,
        "primary_id": primary_id,
        "replica_id": replica_id,
        "config_id": config_id,
    }


def test_bulk_block_perm_replicates_to_replica(ha_bulk_env):
    client = TestClient(ha_bulk_env["app"])
    headers = ha_bulk_env["admin_headers"]
    session_factory = ha_bulk_env["session_factory"]
    primary_adapter, _primary_banned = _ovpn_adapter()
    replica_adapter, replica_banned = _ovpn_adapter()

    def adapter_for_node(node):
        if node.id == ha_bulk_env["replica_id"]:
            return replica_adapter
        return primary_adapter

    exec_mock = MagicMock()
    exec_mock.submit = _immediate_submit

    with (
        patch("app.services.background_tasks._EXECUTOR", exec_mock),
        patch("app.services.bulk_config_ops.SessionLocal", session_factory),
        patch("app.services.bulk_config_ops.get_active_adapter", return_value=primary_adapter),
        patch("app.services.node_sync.policy_sync.get_adapter_for_node", side_effect=adapter_for_node),
    ):
        queued = client.post(
            "/api/configs/bulk",
            headers=headers,
            json={"operation": "block_perm", "config_ids": [ha_bulk_env["config_id"]]},
        )

    assert queued.status_code == 202
    task_id = queued.json()["task_id"]
    status = client.get(f"/api/tasks/{task_id}", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "completed"

    db = session_factory()
    replica_row = (
        db.query(OpenVpnAccessPolicy)
        .filter_by(node_id=ha_bulk_env["replica_id"], client_name="bulk-alice")
        .first()
    )
    db.close()

    assert replica_row is not None
    assert replica_row.is_permanent_blocked is True
    assert "bulk-alice" in replica_banned


def test_patch_description_replicates_to_shadow(ha_bulk_env):
    client = TestClient(ha_bulk_env["app"])
    headers = ha_bulk_env["admin_headers"]
    session_factory = ha_bulk_env["session_factory"]

    response = client.patch(
        f"/api/configs/{ha_bulk_env['config_id']}",
        headers=headers,
        json={"description": "primary note"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "primary note"

    db = session_factory()
    shadow = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == ha_bulk_env["replica_id"],
            VpnConfig.client_name == "bulk-alice",
        )
        .first()
    )
    db.close()
    assert shadow is not None
    assert shadow.description == "primary note"
