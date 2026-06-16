"""Tests for edit-files transfer between nodes."""

from unittest.mock import MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.models import Node, NodeStatus
from tests.conftest import run_async


def _add_remote_node(session, name, node_status=NodeStatus.online):
    node = Node(
        name=name,
        host=f"{name}.example.com",
        port=9100,
        is_local=False,
        status=node_status,
        api_key_hash="hash",
        api_key_encrypted="enc",
    )
    session.add(node)
    session.commit()
    session.refresh(node)
    return node


def test_transfer_edit_files_to_remote_node(api_test_env):
    session = api_test_env["session_factory"]()
    remote = _add_remote_node(session, "remote-a")
    source_adapter = api_test_env["mock_adapter"]
    source_adapter.read_config_file.return_value = "example.com\n"

    target_adapter = MagicMock()
    target_adapter.write_config_file.return_value = None
    target_adapter.apply_config_changes.return_value = "doall ok"

    def adapter_for_node(node):
        if node.id == remote.id:
            return target_adapter
        return source_adapter

    transport = ASGITransport(app=api_test_env["app"])

    with patch("app.services.edit_files_transfer.get_adapter_for_node", side_effect=adapter_for_node):
        async def _call():
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post(
                    "/api/edit-files/transfer",
                    headers=api_test_env["admin_headers"],
                    json={
                        "file_keys": ["include_hosts"],
                        "target_node_ids": [remote.id],
                        "run_doall": True,
                    },
                )

        response = run_async(_call())

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["nodes_success"] == 1
    assert body["files"] == ["include-hosts.txt"]
    source_adapter.read_config_file.assert_called_with("include-hosts.txt")
    target_adapter.write_config_file.assert_called_with("include-hosts.txt", "example.com\n")
    target_adapter.apply_config_changes.assert_called_once()


def test_transfer_skips_offline_target(api_test_env):
    session = api_test_env["session_factory"]()
    offline = _add_remote_node(session, "remote-off", NodeStatus.offline)
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/edit-files/transfer",
                headers=api_test_env["admin_headers"],
                json={
                    "file_keys": ["include_hosts"],
                    "target_node_ids": [offline.id],
                },
            )

    response = run_async(_call())
    assert response.status_code == 200
    body = response.json()
    assert body["nodes_success"] == 0
    assert body["nodes_skipped"] == 1
    assert body["per_node"][0]["status"] == "skipped"


def test_transfer_requires_admin(api_test_env):
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/edit-files/transfer",
                headers=api_test_env["viewer_headers"],
                json={"file_keys": ["include_hosts"], "all_online": True},
            )

    response = run_async(_call())
    assert response.status_code == 403


def test_transfer_unknown_file_key_returns_400(api_test_env):
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/edit-files/transfer",
                headers=api_test_env["admin_headers"],
                json={"file_keys": ["unknown"], "all_online": True},
            )

    response = run_async(_call())
    assert response.status_code == 400
