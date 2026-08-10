"""Parity checks for AWG2 adapter methods and profile branching."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, call, patch

import httpx

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


def test_local_node_adapter_awg2_backup_restore_delegate():
    adapter, _service, awg2 = _local_adapter()
    awg2.export_narrow_backup.return_value = b"backup"
    awg2.apply_runtime.return_value = {"success": True, "synced": ["antizapret-awg"]}

    assert adapter.export_awg2_backup() == b"backup"
    assert adapter.restore_awg2_backup(b"payload") == {"success": True, "synced": ["antizapret-awg"]}

    awg2.export_narrow_backup.assert_called_once_with()
    awg2.import_narrow_backup.assert_called_once_with(b"payload")
    awg2.apply_runtime.assert_called_once_with()
    assert awg2.mock_calls[-2:] == [
        call.import_narrow_backup(b"payload"),
        call.apply_runtime(),
    ]


def test_local_node_adapter_awg2_obfuscation_delegate():
    adapter, _service, awg2 = _local_adapter()
    awg2.get_obfuscation.return_value = {"preset": "medium"}
    awg2.regenerate_obfuscation.return_value = {"preset": "medium", "regen_all": "ok"}
    awg2.apply_obfuscation.return_value = {"preset": "high"}

    assert adapter.get_awg2_obfuscation() == {"preset": "medium"}
    assert adapter.awg2_obfuscation_regenerate()["regen_all"] == "ok"
    assert adapter.awg2_obfuscation_apply(preset="high", template="web", mtu=1280) == {"preset": "high"}

    awg2.get_obfuscation.assert_called_once_with()
    awg2.regenerate_obfuscation.assert_called_once_with()
    awg2.apply_obfuscation.assert_called_once_with(
        preset="high",
        template="web",
        mtu=1280,
        host=None,
        fp=None,
    )


def test_local_node_adapter_awg2_install_stream_delegate():
    adapter, _service, awg2 = _local_adapter()
    awg2.iter_install_stream_events.return_value = iter([{"event": "start"}, {"event": "done"}])

    assert list(
        adapter.awg2_iter_install_stream(
            "install",
            preset="high",
            template="web",
            mtu=1280,
        )
    ) == [{"event": "start"}, {"event": "done"}]

    awg2.iter_install_stream_events.assert_called_once_with(
        "install",
        preset="high",
        template="web",
        mtu=1280,
    )


def test_local_node_adapter_awg2_expiry_map_delegates():
    adapter, _service, awg2 = _local_adapter()
    expiry = {"ivan": datetime(2030, 1, 1, 12, 0, 0)}
    awg2.read_expiry_map.return_value = expiry

    assert adapter.awg2_expiry_map() == expiry
    awg2.read_expiry_map.assert_called_once_with()


def test_remote_node_adapter_awg2_expiry_map_hits_expected_route(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    request_calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        request_calls.append((method, path, kwargs))
        return {"expiry": {"ivan": "2030-01-01T12:00:00", "broken": "not-a-date"}}

    monkeypatch.setattr(adapter, "_request", fake_request)

    assert adapter.awg2_expiry_map() == {"ivan": datetime(2030, 1, 1, 12, 0, 0)}
    assert request_calls == [("GET", "/awg2/expiry", {"timeout": 60.0})]


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


def test_remote_node_adapter_awg2_backup_restore_hit_expected_routes(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    request_calls: list[tuple[str, str, dict]] = []
    byte_calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        request_calls.append((method, path, kwargs))
        return {"success": True, "synced": ["vpn-awg"]}

    def fake_request_bytes(method, path, **kwargs):
        byte_calls.append((method, path, kwargs))
        return b"backup"

    monkeypatch.setattr(adapter, "_request", fake_request)
    monkeypatch.setattr(adapter, "_request_bytes", fake_request_bytes)

    assert adapter.export_awg2_backup() == b"backup"
    assert adapter.restore_awg2_backup(b"payload", "narrow.tar.gz") == {
        "success": True,
        "synced": ["vpn-awg"],
    }

    assert byte_calls == [("POST", "/awg2/backup", {"timeout": 120.0})]
    assert request_calls == [
        (
            "POST",
            "/awg2/restore",
            {
                "files": {"archive": ("narrow.tar.gz", b"payload", "application/gzip")},
                "timeout": 120.0,
            },
        )
    ]


def test_remote_node_adapter_awg2_obfuscation_hit_expected_routes(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    request_calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        request_calls.append((method, path, kwargs))
        return {"preset": "high", "reimport_required": False}

    monkeypatch.setattr(adapter, "_request", fake_request)

    assert adapter.get_awg2_obfuscation()["preset"] == "high"
    assert adapter.awg2_obfuscation_regenerate()["preset"] == "high"
    assert adapter.awg2_obfuscation_apply(preset="high", template="web", mtu=1280, host="ex.com")[
        "preset"
    ] == "high"

    assert request_calls[0] == ("GET", "/awg2/obfuscation", {"timeout": 60.0})
    assert request_calls[1] == ("POST", "/awg2/obfuscation/regenerate", {"timeout": 180.0})
    assert request_calls[2] == (
        "POST",
        "/awg2/obfuscation/apply",
        {
            "json": {"preset": "high", "template": "web", "mtu": 1280, "host": "ex.com"},
            "timeout": 180.0,
        },
    )


def test_local_node_adapter_awg2_monitoring_delegate():
    adapter, _service, awg2 = _local_adapter()
    awg2.get_monitoring.return_value = {"ifaces": [], "clients": [], "stats_available": False}

    assert adapter.get_awg2_monitoring()["stats_available"] is False
    awg2.get_monitoring.assert_called_once_with()


def test_local_node_adapter_awg2_client_stats_delegate():
    adapter, _service, awg2 = _local_adapter()
    awg2.get_client_stats.return_value = {"name": "ivan", "daily": []}

    assert adapter.get_awg2_client_stats("ivan") == {"name": "ivan", "daily": []}
    awg2.get_client_stats.assert_called_once_with("ivan")


def test_remote_node_adapter_awg2_monitoring_hit_expected_routes(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    request_calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        request_calls.append((method, path, kwargs))
        return {"ifaces": [{"name": "vpn-awg"}], "clients": [], "stats_available": True}

    monkeypatch.setattr(adapter, "_request", fake_request)

    assert adapter.get_awg2_monitoring()["stats_available"] is True
    assert request_calls == [("GET", "/awg2/monitoring", {"timeout": 60.0})]


def test_remote_node_adapter_awg2_client_stats_hit_expected_route(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    request_calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        request_calls.append((method, path, kwargs))
        return {"name": "ivan", "daily": []}

    monkeypatch.setattr(adapter, "_request", fake_request)

    assert adapter.get_awg2_client_stats("ivan") == {"name": "ivan", "daily": []}
    assert request_calls == [("GET", "/awg2/clients/ivan/stats", {"timeout": 60.0})]


def test_remote_node_adapter_awg2_install_stream_hits_expected_route(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    stream_calls: list[tuple[str, str, dict]] = []

    class _Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def iter_lines(self):
            yield 'data: {"event":"start","mode":"install"}'
            yield ""
            yield 'data: {"event":"log","line":"step 1"}'
            yield 'data: {"event":"done","success":true,"return_code":0}'

    def fake_stream(method, url, **kwargs):
        stream_calls.append((method, url, kwargs))
        return _Response()

    monkeypatch.setattr("app.services.node_adapter.httpx.stream", fake_stream)

    events = list(
        adapter.awg2_iter_install_stream(
            "install",
            preset="high",
            template="web",
            mtu=1280,
        )
    )

    assert events == [
        {"event": "start", "mode": "install"},
        {"event": "log", "line": "step 1"},
        {"event": "done", "success": True, "return_code": 0},
    ]
    assert len(stream_calls) == 1
    method, url, kwargs = stream_calls[0]
    assert (method, url) == ("GET", "http://10.0.0.2:9100/awg2/install/stream")
    assert kwargs["headers"] == {"X-Node-Key": "k" * 32}
    assert kwargs["params"] == {
        "mode": "install",
        "preset": "high",
        "template": "web",
        "mtu": "1280",
    }
    assert isinstance(kwargs["timeout"], httpx.Timeout)
    assert kwargs["timeout"].connect == 30.0
