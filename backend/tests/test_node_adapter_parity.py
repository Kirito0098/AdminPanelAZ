"""Local vs remote node adapter parity checks."""

import ast
import inspect
import re
from pathlib import Path

import pytest

from app.services.file_editor import EDITABLE_FILES
from app.services.node_adapter import LocalNodeAdapter, NodeAdapter, RemoteNodeAdapter


BACKEND_ROOT = Path(__file__).resolve().parents[1]
NODE_AGENT_MAIN = BACKEND_ROOT / "node_agent" / "main.py"

# RemoteNodeAdapter._request paths (method -> HTTP path template)
REMOTE_ADAPTER_ENDPOINTS: dict[str, str] = {
    "health_check": "GET /health",
    "add_openvpn_client": "POST /clients/openvpn",
    "delete_openvpn_client": "DELETE /clients/openvpn/{client_name}",
    "list_openvpn_clients": "GET /clients/openvpn",
    "add_wireguard_client": "POST /clients/wireguard",
    "delete_wireguard_client": "DELETE /clients/wireguard/{client_name}",
    "list_wireguard_clients": "GET /clients/wireguard",
    "recreate_profiles": "POST /configs/recreate-profiles",
    "create_antizapret_backup": "POST /backups/antizapret",
    "get_profile_files": "GET /profiles/files",
    "get_profile_files_batch": "POST /profiles/files/batch",
    "read_profile_file": "GET /profiles/download",
    "read_config_file": "GET /configs/files/{filename}",
    "write_config_file": "PUT /configs/files/{filename}",
    "apply_config_changes": "POST /configs/apply",
    "get_server_ip": "GET /server/ip",
    "get_service_status": "GET /monitoring/overview",
    "get_openvpn_status_snapshot": "GET /monitoring/overview",
    "get_openvpn_management_events": "GET /openvpn/management/events",
    "get_openvpn_socket_status": "GET /openvpn/management/sockets",
    "parse_wireguard_status": "GET /monitoring/overview",
    "restart_service": "POST /services/restart",
    "get_routing_overview": "GET /routing/overview",
    "get_provider_content": "GET /routing/providers/{filename}",
    "save_provider_content": "PUT /routing/providers/{filename}",
    "set_provider_enabled": "POST /routing/providers/{filename}/enabled",
    "apply_cidr_preset": "POST /routing/presets/{preset_key}/apply",
    "sync_cidr_providers": "POST /routing/sync",
    "read_route_file": "GET /routing/files/{file_key}",
    "write_route_file": "PUT /routing/files/{file_key}",
    "get_route_result_files": "GET /routing/results",
    "get_route_result_content": "GET /routing/results/{key}",
    "get_antizapret_settings": "GET /routing/antizapret-settings",
    "update_antizapret_settings": "PUT /routing/antizapret-settings",
    "get_server_metrics": "GET /server-monitor/metrics",
    "get_server_bandwidth": "GET /server-monitor/bandwidth",
    "list_server_interfaces": "GET /server-monitor/interfaces",
    "block_wireguard_client_runtime": "POST /clients/wireguard/{client_name}/block",
    "unblock_wireguard_client_runtime": "POST /clients/wireguard/{client_name}/unblock",
    "disconnect_openvpn_client": "POST /openvpn/management/disconnect",
    "check_updates": "GET /system/updates",
    "apply_update": "POST /system/update",
    "ensure_openvpn_ban_check": "POST /system/ensure-openvpn-ban-check",
}


def _node_agent_routes() -> set[str]:
    source = NODE_AGENT_MAIN.read_text(encoding="utf-8")
    routes: set[str] = set()
    for match in re.finditer(r'@app\.(get|post|put|delete|patch)\("([^"]+)"\)', source):
        method, path = match.group(1).upper(), match.group(2)
        routes.add(f"{method} {path}")
    return routes


def _abstract_adapter_methods() -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(NodeAdapter)
        if getattr(member, "__isabstractmethod__", False)
    }


def test_local_and_remote_implement_all_node_adapter_methods():
    abstract = _abstract_adapter_methods()
    local_methods = set(dir(LocalNodeAdapter)) - set(dir(object))
    remote_methods = set(dir(RemoteNodeAdapter)) - set(dir(object))
    missing_local = abstract - local_methods
    missing_remote = abstract - remote_methods
    assert not missing_local, f"LocalNodeAdapter missing: {missing_local}"
    assert not missing_remote, f"RemoteNodeAdapter missing: {missing_remote}"


def test_remote_adapter_endpoints_exist_in_node_agent():
    routes = _node_agent_routes()
    missing = []
    for method, endpoint in REMOTE_ADAPTER_ENDPOINTS.items():
        if endpoint not in routes:
            missing.append(f"{method} -> {endpoint}")
    assert not missing, "Missing node_agent routes:\n" + "\n".join(missing)


def test_editable_config_files_allowed_by_antizapret_service():
    from app.services.antizapret import AntiZapretService

    allowed = AntiZapretService._CONFIG_FILES
    editable = set(EDITABLE_FILES.values()) | {"banned_clients"}
    assert editable <= allowed, f"Not allowed via adapter: {sorted(editable - allowed)}"


def test_ensure_openvpn_ban_hook_idempotent(tmp_path: Path):
    from app.services.openvpn_ban_hook import ensure_openvpn_ban_check

    az = tmp_path / "antizapret"
    (az / "config").mkdir(parents=True)
    script = az / "client-connect.sh"
    script.write_text("#!/bin/bash\necho ok\n", encoding="utf-8")

    first = ensure_openvpn_ban_check(az)
    second = ensure_openvpn_ban_check(az)

    assert first["success"] is True
    assert first["changed"] is True
    assert second["changed"] is False
    assert "BEGIN adminpanel ban check" in script.read_text(encoding="utf-8")


def test_access_policy_write_banned_clients_calls_ban_hook_on_adapter():
    from unittest.mock import MagicMock

    from app.services.access_policy import AccessPolicyService

    adapter = MagicMock()
    db = MagicMock()
    svc = AccessPolicyService(db, antizapret_path=Path("/root/antizapret"), adapter=adapter)
    svc.write_banned_clients({"alice"})

    adapter.write_config_file.assert_called_once()
    adapter.ensure_openvpn_ban_check.assert_called_once()


def test_remote_adapter_rotate_api_key_not_in_abstract_interface():
    """rotate_api_key is remote-only (panel DB stores keys for remote nodes)."""
    assert "rotate_api_key" not in _abstract_adapter_methods()
    assert hasattr(RemoteNodeAdapter, "rotate_api_key")


def test_remote_adapter_provision_mtls_not_in_abstract_interface():
    """provision_mtls is remote-only (bootstrap mTLS on node agent)."""
    assert "provision_mtls" not in _abstract_adapter_methods()
    assert hasattr(RemoteNodeAdapter, "provision_mtls")


def test_node_agent_main_imports_without_invalid_key(monkeypatch):
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "x" * 32)
    source = NODE_AGENT_MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(isinstance(node, ast.FunctionDef) and node.name == "health" for node in tree.body)
