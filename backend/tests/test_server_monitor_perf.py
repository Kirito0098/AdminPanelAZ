"""Server monitor probe caches and live-throughput helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import app.services.server_monitor as sm
from app.services.server_monitor import ServerMonitorService


def setup_function():
    sm.clear_server_monitor_caches()


def teardown_function():
    sm.clear_server_monitor_caches()


def test_is_vnstat_available_uses_version_and_caches(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        calls.append(list(args))
        return SimpleNamespace(returncode=0, stdout="vnStat 2.x", stderr="")

    monkeypatch.setattr(sm.shutil, "which", lambda _bin: "/usr/bin/vnstat")
    monkeypatch.setattr(sm.subprocess, "run", fake_run)

    assert sm.is_vnstat_available() is True
    assert sm.is_vnstat_available() is True
    assert len(calls) == 1
    assert calls[0][:2] == ["vnstat", "--version"]

    assert sm.is_vnstat_available(force=True) is True
    assert len(calls) == 2


def test_is_vnstat_available_false_when_missing(monkeypatch):
    monkeypatch.setattr(sm.shutil, "which", lambda _bin: None)
    monkeypatch.setattr(sm, "Path", lambda *_a, **_k: SimpleNamespace(exists=lambda: False))

    assert sm.is_vnstat_available() is False
    assert sm.is_vnstat_available() is False


def test_list_interfaces_cached(monkeypatch):
    builds = {"n": 0}

    def fake_groups():
        builds["n"] += 1
        return {
            "main": ["eth0"],
            "vpn": [],
            "antizapret": [],
            "openvpn": [],
            "wireguard": [],
        }

    monkeypatch.setattr(sm, "collect_interface_groups", fake_groups)
    monkeypatch.setattr(sm, "detect_primary_interface", lambda: "eth0")
    monkeypatch.setattr(sm, "interface_exists", lambda name: name == "eth0")
    monkeypatch.setattr(sm, "is_vnstat_available", lambda **_k: False)

    svc = ServerMonitorService()
    first = svc.list_interfaces()
    second = svc.list_interfaces()
    assert first == second
    assert builds["n"] == 1
    assert first["interfaces"] == ["eth0"]

    forced = svc.list_interfaces(force=True)
    assert builds["n"] == 2
    assert forced["interfaces"] == ["eth0"]


def test_get_live_throughput_skips_discovery_when_names_given(monkeypatch):
    svc = ServerMonitorService()
    listed = {"n": 0}

    def boom_list(*_a, **_k):
        listed["n"] += 1
        raise AssertionError("list_interfaces must not run when names are provided")

    monkeypatch.setattr(svc, "list_interfaces", boom_list)
    monkeypatch.setattr(
        svc,
        "sample_interface_throughput",
        lambda names, **_k: [{"name": names[0], "rx_mbps": 1.5, "tx_mbps": 0.5, "is_up": True}],
    )

    out = svc.get_live_throughput(interface_names=["vpn"], interval=0.3, max_interfaces=1)
    assert listed["n"] == 0
    assert out["primary_interface"] == "vpn"
    assert out["interfaces"][0]["rx_mbps"] == 1.5


def test_ws_tick_prefers_live_throughput_not_bandwidth():
    """Guard the WS contract: live sample API is what the router should call."""
    from app.routers import server_monitor as router_mod

    adapter = MagicMock()
    adapter.get_server_metrics.return_value = {
        "cpu_percent": 10.0,
        "memory_percent": 20.0,
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    adapter.get_server_live_throughput.return_value = {
        "interfaces": [{"name": "eth0", "rx_mbps": 3.0, "tx_mbps": 1.0, "is_up": True}],
    }

    metrics = adapter.get_server_metrics()
    live = adapter.get_server_live_throughput(
        interval=router_mod._WS_THROUGHPUT_INTERVAL_S,
        max_interfaces=1,
        interface_names=["eth0"],
    )
    adapter.get_server_bandwidth.assert_not_called()
    assert metrics["cpu_percent"] == 10.0
    assert live["interfaces"][0]["rx_mbps"] == 3.0
