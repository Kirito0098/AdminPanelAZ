"""AntiZapretService.ensure_openvpn_multihome: restart only when needed after doall."""

import pytest

from app.services import antizapret_settings
from app.services.antizapret import AntiZapretService
from app.services.node_adapter import RemoteNodeAdapter
from app.services.node_sync import openvpn_restart

WITH_MH = "port 1194\nproto udp\nmultihome\ndev tun\n"
WITHOUT_MH = "port 1194\nproto udp\ndev tun\n"


@pytest.fixture
def service(monkeypatch, tmp_path):
    svc = AntiZapretService(base_path=tmp_path)
    confs: dict[str, str] = {}
    restarts: list[int] = []

    monkeypatch.setattr(svc, "list_openvpn_server_confs", lambda: list(confs))
    monkeypatch.setattr(svc, "read_openvpn_server_conf", lambda name: confs[name])
    monkeypatch.setattr(svc, "write_openvpn_server_conf", lambda name, content: confs.__setitem__(name, content))
    monkeypatch.setattr(antizapret_settings, "read_protocol_enable_flags", lambda _path: {})

    def _restart(_adapter, *, protocol_flags=None):
        restarts.append(1)
        return {"restarted": ["openvpn-server@antizapret-udp"], "skipped": [], "failed": [], "success": True}

    monkeypatch.setattr(openvpn_restart, "restart_all_openvpn_servers", _restart)
    svc._test_confs = confs
    svc._test_restarts = restarts
    return svc


def test_unchanged_confs_skip_restart_when_not_forced(service):
    service._test_confs["antizapret-udp.conf"] = WITH_MH

    result = service.ensure_openvpn_multihome(True, restart_if_unchanged=False)

    assert service._test_restarts == []
    assert result["success"] is True
    assert result["patched"] == []
    assert result["restart"] is None
    assert result["on_disk"] is True


def test_patched_confs_restart_even_when_not_forced(service):
    service._test_confs["antizapret-udp.conf"] = WITHOUT_MH

    result = service.ensure_openvpn_multihome(True, restart_if_unchanged=False)

    assert service._test_restarts == [1]
    assert result["patched"] == ["antizapret-udp.conf"]
    assert result["restart"]["restarted"] == ["openvpn-server@antizapret-udp"]


def test_default_still_restarts_unchanged_confs(service):
    service._test_confs["antizapret-udp.conf"] = WITH_MH

    result = service.ensure_openvpn_multihome(True)

    assert service._test_restarts == [1]
    assert result["patched"] == []


def test_remote_adapter_sends_restart_if_unchanged(monkeypatch):
    adapter = RemoteNodeAdapter(host="127.0.0.1", port=9100, api_key="k" * 32)
    calls: list[dict] = []
    monkeypatch.setattr(adapter, "_request", lambda method, path, **kw: calls.append({"path": path, **kw}) or {})

    adapter.ensure_openvpn_multihome(True, restart_if_unchanged=False)

    assert calls[0]["path"] == "/openvpn/multihome"
    assert calls[0]["json"] == {"enabled": True, "restart_if_unchanged": False}
