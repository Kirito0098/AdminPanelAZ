"""AZ-WARP 1.5.1: donor links from `warperslave link` and forced kresd restart."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.routers import warper as warper_router
from app.schemas import WarperModeLinkUpdate, WarperModeSlaveUpdate
from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter
from app.services.warper import WarperService, extract_proxy_link

SS = "ss://MjAyMi1ibGFrZTM@203.0.113.5:8444#warperslave"
VLESS = "vless://uuid@203.0.113.5:443?security=reality&sni=example.com#warperslave"
HY2 = "hy2://pass@203.0.113.5:8443?sni=example.com&obfs=salamander#warperslave"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"  {SS}\n", SS),
        (f"Shadowsocks: {SS}", SS),
        (f"VLESS+Reality: {VLESS}", VLESS),
        (f"warper mode hy2 '{HY2}'", HY2),
        (" 203.0.113.5 ", "203.0.113.5"),
        (None, ""),
    ],
)
def test_extract_proxy_link(text, expected):
    assert extract_proxy_link(text) == expected


@pytest.fixture
def router_adapter(monkeypatch):
    adapter = MagicMock()
    adapter.set_warper_mode_slave.return_value = {"message": "slave"}
    adapter.set_warper_mode_vless.return_value = {"message": "vless"}
    adapter.set_warper_mode_hy2.return_value = {"message": "hy2"}
    adapter.warper_restart_kresd.return_value = {"message": "kresd"}
    node = SimpleNamespace(id=1, name="node-1", host="203.0.113.1")
    monkeypatch.setattr(warper_router, "get_active_adapter", lambda _db: adapter)
    monkeypatch.setattr(warper_router, "get_active_node", lambda _db: node)
    return adapter


def _slave(link: str):
    return warper_router.warper_settings_mode_slave(WarperModeSlaveUpdate(link=link), _=MagicMock(), db=MagicMock())


def test_slave_field_with_vless_link_switches_to_vless(router_adapter):
    assert _slave(f"VLESS+Reality: {VLESS}").message == "vless"
    router_adapter.set_warper_mode_vless.assert_called_once_with(VLESS)
    router_adapter.set_warper_mode_slave.assert_not_called()


@pytest.mark.parametrize("link", [HY2, HY2.replace("hy2://", "hysteria2://")])
def test_slave_field_with_hy2_link_switches_to_hy2(router_adapter, link):
    assert _slave(f"warper mode hy2 '{link}'").message == "hy2"
    router_adapter.set_warper_mode_hy2.assert_called_once_with(link)


def test_slave_field_with_ss_output_line_sends_bare_link(router_adapter):
    assert _slave(f"Shadowsocks: {SS}").message == "slave"
    router_adapter.set_warper_mode_slave.assert_called_once_with(link=SS)


def test_vless_and_hy2_fields_accept_output_lines(router_adapter):
    payload = WarperModeLinkUpdate(link=f"VLESS+Reality: {VLESS}")
    warper_router.warper_settings_mode_vless(payload, _=MagicMock(), db=MagicMock())
    payload = WarperModeLinkUpdate(link=f"Hysteria2: {HY2}")
    warper_router.warper_settings_mode_hy2(payload, _=MagicMock(), db=MagicMock())

    router_adapter.set_warper_mode_vless.assert_called_once_with(VLESS)
    router_adapter.set_warper_mode_hy2.assert_called_once_with(HY2)


def test_service_slave_takes_link_from_output_line(monkeypatch):
    setter = MagicMock(return_value={"message": "OK"})
    api = SimpleNamespace(version="1.5.1", set_mode_slave=setter)
    service = WarperService()
    monkeypatch.setattr(service, "_api_client", lambda: api)

    service.set_mode_slave(link=f"Shadowsocks: {SS}")

    setter.assert_called_once_with(SS)


@pytest.fixture
def fake_runner(monkeypatch):
    run_warper = MagicMock(return_value=SimpleNamespace(ok=True, data=None, message=""))
    package = ModuleType("warper_api")
    runner = ModuleType("warper_api._runner")
    runner.run_warper = run_warper
    package._runner = runner
    monkeypatch.setitem(sys.modules, "warper_api", package)
    monkeypatch.setitem(sys.modules, "warper_api._runner", runner)
    return run_warper


def _kresd_service(monkeypatch, *, version: str, active: bool) -> WarperService:
    api = SimpleNamespace(version=version, is_active=lambda: active)
    service = WarperService()
    monkeypatch.setattr(service, "_api_client", lambda: api)
    return service


def test_restart_kresd_runs_forced_sync(monkeypatch, fake_runner):
    service = _kresd_service(monkeypatch, version="1.5.1", active=True)

    assert service.restart_kresd() == {"message": "kresd перезапущен"}
    fake_runner.assert_called_once_with("sync", "--force", timeout=120)


def test_restart_kresd_requires_az_warp_1_5_1(monkeypatch, fake_runner):
    service = _kresd_service(monkeypatch, version="1.5.0", active=True)

    with pytest.raises(HTTPException) as exc:
        service.restart_kresd()

    assert "1.5.1" in exc.value.detail
    fake_runner.assert_not_called()


def test_restart_kresd_refuses_when_az_warp_inactive(monkeypatch, fake_runner):
    service = _kresd_service(monkeypatch, version="1.5.1", active=False)

    with pytest.raises(HTTPException) as exc:
        service.restart_kresd()

    assert exc.value.status_code == 409
    fake_runner.assert_not_called()


def test_restart_kresd_reports_failure(monkeypatch, fake_runner):
    fake_runner.return_value = SimpleNamespace(ok=False, data=None, message="Не удалось перезапустить kresd")
    service = _kresd_service(monkeypatch, version="1.5.1", active=True)

    with pytest.raises(HTTPException) as exc:
        service.restart_kresd()

    assert exc.value.status_code == 502
    assert exc.value.detail == "Не удалось перезапустить kresd"


def test_restart_kresd_adapters_and_router(monkeypatch, router_adapter):
    warper = MagicMock()
    LocalNodeAdapter(service=MagicMock(), warper=warper, awg2=MagicMock()).warper_restart_kresd()
    warper.restart_kresd.assert_called_once_with()

    remote = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    calls = []
    monkeypatch.setattr(remote, "_warper_agent_request", lambda method, path, **kw: calls.append((method, path, kw)))
    remote.warper_restart_kresd()
    assert calls == [("POST", "/warper/kresd/restart", {"timeout": 150.0})]

    assert warper_router.warper_kresd_restart(_=MagicMock(), db=MagicMock()).message == "kresd"
