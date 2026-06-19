"""Integration tests for HA config file auto-sync hooks (step B.2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.models import AppSetting, Node, NodeStatus, NodeSyncGroup, SyncStatus
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


@pytest.fixture()
def ha_config_env(api_test_env):
    session_factory = api_test_env["session_factory"]
    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica = Node(name="replica-config", host="10.0.0.30", port=9100, status=NodeStatus.online)
    db.add(replica)
    db.commit()
    db.refresh(replica)

    group = NodeSyncGroup(
        name="HA config",
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
    db.close()

    _set_active_node(session_factory, primary_id)
    yield {
        **api_test_env,
        "primary_id": primary_id,
        "replica_id": replica_id,
    }


def _adapter_for_node(primary_id, primary_adapter, replica_id, replica_adapter):
    def resolve(node):
        if node.id == replica_id:
            return replica_adapter
        if node.id == primary_id:
            return primary_adapter
        return MagicMock()

    return resolve


def test_settings_patch_replicates_changed_lists(ha_config_env):
    client = TestClient(ha_config_env["app"])
    primary_adapter, primary_store = _config_adapter()
    replica_adapter, replica_store = _config_adapter()
    adapter_for_node = _adapter_for_node(
        ha_config_env["primary_id"],
        primary_adapter,
        ha_config_env["replica_id"],
        replica_adapter,
    )

    with (
        patch("app.routers.settings.get_active_adapter", return_value=primary_adapter),
        patch("app.services.node_manager.get_active_adapter", return_value=primary_adapter),
        patch("app.routers.settings.admin_notify_service.send_settings_change"),
        patch("app.services.edit_files_transfer.get_adapter_for_node", side_effect=adapter_for_node),
    ):
        response = client.patch(
            "/api/settings",
            headers=ha_config_env["admin_headers"],
            json={"include_hosts": "blocked.example\n", "allow_ips": "10.0.0.0/8\n"},
        )

    assert response.status_code == 200
    assert primary_store["include-hosts.txt"] == "blocked.example\n"
    assert primary_store["allow-ips.txt"] == "10.0.0.0/8\n"
    assert replica_store["include-hosts.txt"] == "blocked.example\n"
    assert replica_store["allow-ips.txt"] == "10.0.0.0/8\n"
    primary_adapter.apply_config_changes.assert_called_once()
    replica_adapter.apply_config_changes.assert_called_once()


def test_edit_files_put_replicates_to_replica(ha_config_env):
    client = TestClient(ha_config_env["app"])
    primary_adapter, primary_store = _config_adapter()
    replica_adapter, replica_store = _config_adapter()
    adapter_for_node = _adapter_for_node(
        ha_config_env["primary_id"],
        primary_adapter,
        ha_config_env["replica_id"],
        replica_adapter,
    )

    with (
        patch("app.routers.edit_files.get_active_adapter", return_value=primary_adapter),
        patch("app.services.edit_files_transfer.get_adapter_for_node", side_effect=adapter_for_node),
    ):
        response = client.put(
            "/api/edit-files/include_hosts",
            headers=ha_config_env["admin_headers"],
            json={"content": "site.example\n"},
        )

    assert response.status_code == 200
    assert primary_store["include-hosts.txt"] == "site.example\n"
    assert replica_store["include-hosts.txt"] == "site.example\n"
    replica_adapter.apply_config_changes.assert_called_once()


def test_edit_files_batch_replicates_without_doall_when_disabled(ha_config_env):
    client = TestClient(ha_config_env["app"])
    primary_adapter, primary_store = _config_adapter()
    replica_adapter, replica_store = _config_adapter()
    adapter_for_node = _adapter_for_node(
        ha_config_env["primary_id"],
        primary_adapter,
        ha_config_env["replica_id"],
        replica_adapter,
    )
    settings = Settings(
        app_env="development",
        node_sync_auto_replicate_config_files=True,
        node_sync_replicate_doall=False,
    )

    with (
        patch("app.routers.edit_files.get_active_adapter", return_value=primary_adapter),
        patch("app.services.edit_files_transfer.get_adapter_for_node", side_effect=adapter_for_node),
        patch("app.services.node_sync.config_sync.get_settings", return_value=settings),
    ):
        response = client.post(
            "/api/edit-files/batch",
            headers=ha_config_env["admin_headers"],
            json={
                "files": {"exclude_ips": "192.0.2.0/24\n"},
                "run_doall": True,
            },
        )

    assert response.status_code == 200
    assert primary_store["exclude-ips.txt"] == "192.0.2.0/24\n"
    assert replica_store["exclude-ips.txt"] == "192.0.2.0/24\n"
    primary_adapter.apply_config_changes.assert_called_once()
    replica_adapter.apply_config_changes.assert_not_called()


def test_config_replicate_skipped_when_auto_replicate_disabled(ha_config_env):
    client = TestClient(ha_config_env["app"])
    primary_adapter, primary_store = _config_adapter()
    replica_adapter, replica_store = _config_adapter()
    adapter_for_node = _adapter_for_node(
        ha_config_env["primary_id"],
        primary_adapter,
        ha_config_env["replica_id"],
        replica_adapter,
    )
    settings = Settings(
        app_env="development",
        node_sync_auto_replicate_config_files=False,
        node_sync_replicate_doall=True,
    )

    with (
        patch("app.routers.edit_files.get_active_adapter", return_value=primary_adapter),
        patch("app.services.edit_files_transfer.get_adapter_for_node", side_effect=adapter_for_node),
        patch("app.services.node_sync.config_sync.get_settings", return_value=settings),
    ):
        response = client.put(
            "/api/edit-files/include_hosts",
            headers=ha_config_env["admin_headers"],
            json={"content": "local-only.example\n"},
        )

    assert response.status_code == 200
    assert primary_store["include-hosts.txt"] == "local-only.example\n"
    assert replica_store == {}
    replica_adapter.write_config_file.assert_not_called()
