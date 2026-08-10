"""Parity checks for AWG2 adapter methods and profile branching."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models import VpnType
from app.services import awg2 as awg2_module
from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter
from app.services.profile_download_name import build_profile_download_filename


def _local_adapter() -> tuple[LocalNodeAdapter, MagicMock, MagicMock]:
    service = MagicMock()
    warper = MagicMock()
    awg2 = MagicMock()
    return LocalNodeAdapter(service=service, warper=warper, awg2=awg2), service, awg2


def test_local_node_adapter_awg2_methods_delegate():
    adapter, _service, awg2 = _local_adapter()
    awg2.add_client.return_value = "added"
    awg2.delete_client.return_value = "deleted"
    awg2.list_clients.return_value = ["alice", "bob"]

    assert adapter.awg2_add_client("alice") == "added"
    assert adapter.awg2_delete_client("alice") == "deleted"
    assert adapter.awg2_list_clients("vpn") == ["alice", "bob"]
    awg2.add_client.assert_called_once_with("alice")
    awg2.delete_client.assert_called_once_with("alice")
    awg2.list_clients.assert_called_once_with("vpn")


def test_local_node_adapter_awg2_archive_runtime_delegate():
    adapter, _service, awg2 = _local_adapter()
    awg2.export_state_archive.return_value = b"archive"
    awg2.apply_runtime.return_value = {"success": True}

    assert adapter.export_awg2_state_archive() == b"archive"
    adapter.import_awg2_state_archive(b"payload")
    assert adapter.apply_awg2_runtime() == {"success": True}

    awg2.export_state_archive.assert_called_once_with()
    awg2.import_state_archive.assert_called_once_with(b"payload")
    awg2.apply_runtime.assert_called_once_with()


def test_local_node_adapter_get_profile_files_branches_awg2():
    adapter, service, awg2 = _local_adapter()
    service.get_profile_files.return_value = [{"path": "ovpn"}]
    awg2.get_profile_files.return_value = [{"path": "awg2"}]

    assert adapter.get_profile_files("alice", VpnType.amneziawg2) == [{"path": "awg2"}]
    assert adapter.get_profile_files("alice", VpnType.openvpn) == [{"path": "ovpn"}]
    awg2.get_profile_files.assert_called_once_with("alice")
    service.get_profile_files.assert_called_once_with("alice", VpnType.openvpn)


def test_local_node_adapter_read_profile_file_branches_awg2(tmp_path):
    adapter, service, awg2 = _local_adapter()
    awg2_root = tmp_path / "clients"
    awg2_file = awg2_root / "antizapret" / "antizapret-alice-am.conf"
    awg2_file.parent.mkdir(parents=True)
    awg2_file.write_text("awg2\n")
    awg2.read_profile_file.return_value = "awg2\n"
    with (
        patch.object(awg2_module, "AWG2_CLIENT_DIR", awg2_root),
    ):
        assert adapter.read_profile_file(str(awg2_file)) == "awg2\n"
    awg2.read_profile_file.assert_called_once_with(str(awg2_file))
    service.read_profile_file.assert_not_called()


def test_build_profile_download_filename_handles_awg2_paths():
    assert build_profile_download_filename(
        "alice",
        path="/opt/antizapret-awg/clients/antizapret/antizapret-alice-am.conf",
    ) == "AWG2-AZ-alice.conf"
    assert build_profile_download_filename(
        "alice",
        path="/opt/antizapret-awg/clients/vpn/vpn-alice-am.conf",
    ) == "AWG2-VPN-alice.conf"
    assert build_profile_download_filename(
        "alice",
        protocol="amneziawg2",
        variant="antizapret",
        path="/opt/antizapret-awg/clients/antizapret/antizapret-alice.vpn",
    ) == "AWG2-AZ-alice.vpn"
    assert build_profile_download_filename(
        "alice",
        protocol="amneziawg2",
        variant="vpn",
        path="/opt/antizapret-awg/clients/vpn/vpn-alice-vpnuri.txt",
    ) == "AWG2-VPN-alice-vpnuri.txt"


def test_remote_node_adapter_awg2_methods_hit_expected_routes(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/clients/amneziawg2":
            return {"clients": ["alice"]}
        return {"message": "ok"}

    monkeypatch.setattr(adapter, "_request", fake_request)

    assert adapter.awg2_add_client("alice") == "ok"
    assert adapter.awg2_delete_client("alice") == "ok"
    assert adapter.awg2_list_clients("vpn") == ["alice"]
    assert calls[0][0:2] == ("POST", "/clients/amneziawg2")
    assert calls[0][2]["json"] == {"client_name": "alice"}
    assert calls[1][0:2] == ("DELETE", "/clients/amneziawg2/alice")
    assert calls[2][0:2] == ("GET", "/clients/amneziawg2")
    assert calls[2][2]["params"] == {"tunnel": "vpn"}


def test_remote_node_adapter_awg2_archive_runtime_hit_expected_routes(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    request_calls: list[tuple[str, str, dict]] = []
    byte_calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        request_calls.append((method, path, kwargs))
        return {"success": True}

    def fake_request_bytes(method, path, **kwargs):
        byte_calls.append((method, path, kwargs))
        return b"archive"

    monkeypatch.setattr(adapter, "_request", fake_request)
    monkeypatch.setattr(adapter, "_request_bytes", fake_request_bytes)

    assert adapter.export_awg2_state_archive() == b"archive"
    adapter.import_awg2_state_archive(b"payload")
    assert adapter.apply_awg2_runtime() == {"success": True}

    assert byte_calls == [("GET", "/awg2/state/archive", {"timeout": 120.0})]
    assert request_calls[0] == (
        "POST",
        "/awg2/state/archive",
        {"content": b"payload", "timeout": 120.0},
    )
    assert request_calls[1] == ("POST", "/awg2/runtime/apply", {"timeout": 60.0})
