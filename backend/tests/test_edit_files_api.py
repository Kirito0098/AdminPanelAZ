"""Edit-files API tests (ported from AdminAntizapret test_edit_files_page_context)."""

from httpx import ASGITransport, AsyncClient

from app.services.file_editor import EDITABLE_FILES, FILE_TITLES
from tests.conftest import run_async


def test_list_edit_files_returns_catalog(api_test_env):
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/edit-files", headers=api_test_env["admin_headers"])

    response = run_async(_call())
    assert response.status_code == 200
    payload = response.json()
    keys = {item["key"] for item in payload}
    assert keys == set(EDITABLE_FILES.keys())
    for item in payload:
        assert item["title"] == FILE_TITLES.get(item["key"], item["key"])


def test_viewer_cannot_list_edit_files(api_test_env):
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/edit-files", headers=api_test_env["viewer_headers"])

    response = run_async(_call())
    assert response.status_code == 403


def test_read_edit_file_via_adapter(api_test_env):
    adapter = api_test_env["mock_adapter"]
    adapter.read_config_file.return_value = "a.example.com\n"
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/edit-files/include_hosts", headers=api_test_env["admin_headers"])

    response = run_async(_call())
    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "include_hosts"
    assert body["content"] == "a.example.com\n"
    adapter.read_config_file.assert_called_with("include-hosts.txt")


def test_save_edit_file_applies_changes(api_test_env):
    adapter = api_test_env["mock_adapter"]
    adapter.apply_config_changes.return_value = "doall ok"
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.put(
                "/api/edit-files/include_hosts",
                headers=api_test_env["admin_headers"],
                json={"content": "example.com\n"},
            )

    response = run_async(_call())
    assert response.status_code == 200
    adapter.write_config_file.assert_called_with("include-hosts.txt", "example.com\n")
    adapter.apply_config_changes.assert_called_once()


def test_unknown_file_key_returns_400(api_test_env):
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/edit-files/unknown-list", headers=api_test_env["admin_headers"])

    response = run_async(_call())
    assert response.status_code == 400


def test_editable_file_groups_security_and_routing():
    security_keys = {"allow_ips", "deny_ips"}
    routing_keys = {"include_ips", "exclude_ips", "forward_ips", "drop_ips"}
    domain_keys = {"include_hosts", "exclude_hosts", "remove_hosts"}

    assert security_keys.issubset(EDITABLE_FILES)
    assert routing_keys.issubset(EDITABLE_FILES)
    assert domain_keys.issubset(EDITABLE_FILES)
