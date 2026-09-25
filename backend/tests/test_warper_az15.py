"""AZ-WARP 1.5 compatibility: modes, sing-box, auto-resolve, update marker, adapter routes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services import warper as warper_module
from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter
from app.services.warper import WarperService, az_warp_mode, is_update_pending


class _FakeApi:
    def __init__(self, version: str = "1.5.0", **methods):
        self.version = version
        self.calls: list[tuple[str, tuple]] = []
        for name, value in methods.items():
            setattr(self, name, self._recorder(name, value))

    def _recorder(self, name, value):
        def method(*args):
            self.calls.append((name, args))
            return value(*args) if callable(value) else value

        return method


def _service(api: _FakeApi, monkeypatch) -> WarperService:
    service = WarperService()
    monkeypatch.setattr(service, "_api_client", lambda: api)
    return service


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("y", "all"),
        ("2", "all"),
        ("3", "selective"),
        ("4", "selective"),
        ("1", "off"),
        ("n", "off"),
        ("", "off"),
        (None, "off"),
    ],
)
def test_az_warp_mode(value, expected):
    assert az_warp_mode(value) == expected


def test_update_pending_marker(tmp_path: Path, monkeypatch):
    version = tmp_path / "version"
    marker = tmp_path / ".update-complete"
    monkeypatch.setattr(warper_module, "WARPER_VERSION_FILE", version)
    monkeypatch.setattr(warper_module, "WARPER_UPDATE_MARKER", marker)

    version.write_text("1.4.9\n")
    assert is_update_pending() is False

    version.write_text("1.5.0\n")
    assert is_update_pending() is True

    marker.write_text("1.5.0\n")
    assert is_update_pending() is False


def test_health_never_reports_conflict(monkeypatch):
    monkeypatch.setattr(
        warper_module,
        "detect_warper_installation",
        lambda: {
            "installed": True,
            "warper_bin": True,
            "warper_script": True,
            "warper_api": True,
            "missing_components": [],
        },
    )
    monkeypatch.setattr(
        warper_module,
        "_antizapret_warp_modes",
        lambda: {"antizapret_warp_mode": "all", "vpn_warp_mode": "off"},
    )
    monkeypatch.setattr(warper_module, "is_update_pending", lambda: False)
    api = _FakeApi(is_active=True)
    health = _service(api, monkeypatch).get_health()
    assert health["conflict_antizapret_warp"] is False
    assert health["antizapret_warp_mode"] == "all"
    assert health["active"] is True


def test_status_strips_slave_password(monkeypatch):
    api = _FakeApi(get_status={"mode": "slave", "slave": {"host": "h", "password": "secret"}})
    status = _service(api, monkeypatch).get_status()
    assert status["slave"] == {"host": "h"}


def test_set_mode_slave_link(monkeypatch):
    api = _FakeApi(set_mode_slave={"message": "OK"})
    service = _service(api, monkeypatch)
    service.set_mode_slave(link="ss://abc@host:8388")
    assert api.calls == [("set_mode_slave", ("ss://abc@host:8388",))]


def test_set_mode_slave_link_requires_1_5(monkeypatch):
    api = _FakeApi(version="1.4.2", set_mode_slave={"message": "OK"})
    with pytest.raises(HTTPException) as exc:
        _service(api, monkeypatch).set_mode_slave(link="ss://abc@host:8388")
    assert exc.value.status_code == 502


def test_set_mode_slave_manual(monkeypatch):
    api = _FakeApi(set_mode_slave={"message": "OK"})
    _service(api, monkeypatch).set_mode_slave("1.2.3.4", 8388, "key")
    assert api.calls == [("set_mode_slave", ("1.2.3.4", 8388, "key"))]


def test_set_mode_warp_key_sources(monkeypatch):
    api = _FakeApi(set_mode_warp={"message": "OK"})
    service = _service(api, monkeypatch)
    service.set_mode_warp("wgcf")
    with pytest.raises(HTTPException):
        service.set_mode_warp("bogus")
    assert api.calls == [("set_mode_warp", ("wgcf",))]


def test_new_modes_validate_links(monkeypatch):
    api = _FakeApi(set_mode_vless={"message": "OK"}, set_mode_hy2={"message": "OK"})
    service = _service(api, monkeypatch)
    service.set_mode_vless("vless://uuid@host:443")
    service.set_mode_hy2("hysteria2://pw@host:443")
    with pytest.raises(HTTPException):
        service.set_mode_vless("http://x")
    with pytest.raises(HTTPException):
        service.set_mode_hy2("vless://x")
    assert [name for name, _ in api.calls] == ["set_mode_vless", "set_mode_hy2"]


def test_openvpn_mode_requires_password_with_username(monkeypatch):
    api = _FakeApi(set_mode_openvpn={"message": "OK"})
    service = _service(api, monkeypatch)
    with pytest.raises(HTTPException):
        service.set_mode_openvpn("/root/a.ovpn", "user", None)
    with pytest.raises(HTTPException):
        service.set_mode_openvpn("/root/a.conf")
    service.set_mode_openvpn("/root/a.ovpn", "user", "pw")
    service.set_mode_openvpn("/root/b.ovpn")
    assert api.calls == [
        ("set_mode_openvpn", ("/root/a.ovpn", "user", "pw")),
        ("set_mode_openvpn", ("/root/b.ovpn", None, None)),
    ]


def test_missing_api_method_reports_min_version(monkeypatch):
    api = _FakeApi()
    with pytest.raises(HTTPException) as exc:
        _service(api, monkeypatch).resync()
    assert exc.value.status_code == 502
    assert "1.5.0" in exc.value.detail


def test_singbox_action_uses_api_then_systemctl_fallback(monkeypatch):
    fallback = MagicMock(return_value={"success": True})
    monkeypatch.setattr(warper_module, "_singbox_systemctl", fallback)

    api = _FakeApi(singbox_restart={"message": "ok"})
    service = _service(api, monkeypatch)
    service.singbox_action("restart")
    assert api.calls == [("singbox_restart", ())]
    fallback.assert_not_called()

    service.singbox_action("stop")
    fallback.assert_called_once_with("stop")

    with pytest.raises(HTTPException):
        service.singbox_action("reboot")


def test_singbox_status_normalized(monkeypatch):
    api = _FakeApi(
        singbox_status={"active": "active", "enabled": "disabled", "version": "1.11.0", "mtu": "1420"}
    )
    status = _service(api, monkeypatch).singbox_status()
    assert status["active"] is True
    assert status["enabled"] is False
    assert status["state"] == "active"
    assert status["mtu"] == 1420


def test_auto_resolve_parsing(monkeypatch):
    api = _FakeApi(get_auto_resolve=SimpleNamespace(ok=True, data=None, message="enabled"))
    assert _service(api, monkeypatch).get_auto_resolve() == {"enabled": True}

    api = _FakeApi(get_auto_resolve=False)
    assert _service(api, monkeypatch).get_auto_resolve() == {"enabled": False}


def test_resolve_clean_normalizes_domain(monkeypatch):
    api = _FakeApi(resolve_clean={"message": "OK"})
    service = _service(api, monkeypatch)
    service.resolve_clean("*.Example.COM")
    service.resolve_clean("")
    assert api.calls == [("resolve_clean", ("example.com",)), ("resolve_clean", (None,))]


def test_local_adapter_delegates_new_warper_ops():
    warper = MagicMock()
    adapter = LocalNodeAdapter(service=MagicMock(), warper=warper, awg2=MagicMock())

    adapter.set_warper_mode_vless("vless://x")
    adapter.set_warper_mode_hy2("hy2://x")
    adapter.warper_resync()
    adapter.warper_update_lists()
    adapter.get_warper_auto_resolve()
    adapter.get_warper_subnets()
    adapter.get_warper_singbox_status()

    warper.set_mode_vless.assert_called_once_with("vless://x")
    warper.set_mode_hy2.assert_called_once_with("hy2://x")
    warper.resync.assert_called_once_with()
    warper.update_lists.assert_called_once_with()
    warper.get_auto_resolve.assert_called_once_with()
    warper.get_subnets.assert_called_once_with()
    warper.singbox_status.assert_called_once_with()


def test_remote_adapter_new_warper_routes(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    calls: list[tuple[str, str]] = []

    def fake_agent_request(method, path, **kwargs):
        calls.append((method, path))
        return {"message": "OK", "enabled": True, "routes": [], "subnets": {}}

    monkeypatch.setattr(adapter, "_warper_agent_request", fake_agent_request)

    adapter.set_warper_mode_vless("vless://x")
    adapter.set_warper_mode_hy2("hy2://x")
    adapter.warper_resync()
    adapter.warper_update_lists()
    adapter.get_warper_auto_resolve()
    adapter.get_warper_ip_routes()
    adapter.get_warper_subnets()
    adapter.get_warper_singbox_status()

    assert calls == [
        ("POST", "/warper/settings/mode/vless"),
        ("POST", "/warper/settings/mode/hy2"),
        ("POST", "/warper/resync"),
        ("POST", "/warper/domains/update-lists"),
        ("GET", "/warper/resolve"),
        ("GET", "/warper/ip-routes"),
        ("GET", "/warper/subnets"),
        ("GET", "/warper/singbox/status"),
    ]


def test_remote_adapter_maps_missing_route_to_agent_update(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)

    def fake_request(method, path, **kwargs):
        raise HTTPException(status_code=404, detail="Not Found")

    monkeypatch.setattr(adapter, "_request", fake_request)
    with pytest.raises(HTTPException) as exc:
        adapter.warper_resync()
    assert exc.value.status_code == 503
    assert "node agent" in exc.value.detail
