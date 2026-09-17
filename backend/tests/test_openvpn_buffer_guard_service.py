from __future__ import annotations

from unittest.mock import MagicMock

import pytest

try:
    import sqlalchemy  # type: ignore[unused-import]
except ModuleNotFoundError:  # pragma: no cover - dev/test env only
    sqlalchemy = None  # type: ignore[assignment]
else:  # pragma: no cover
    from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter

from app.services.openvpn_buffer_guard import normalize_watch_unit, journal_unit_name


def test_normalize_watch_unit():
    assert normalize_watch_unit("antizapret-udp") == "antizapret-udp"
    assert normalize_watch_unit("openvpn-server@vpn-udp") == "vpn-udp"
    assert normalize_watch_unit("openvpn-server@vpn-udp.service") == "vpn-udp"
    assert normalize_watch_unit(" vpn-tcp.service ") == "vpn-tcp"
    assert normalize_watch_unit("evil") is None


def test_journal_unit_name_roundtrip():
    assert journal_unit_name("antizapret-udp") == "openvpn-server@antizapret-udp.service"
    assert journal_unit_name("openvpn-server@vpn-udp.service") == "openvpn-server@vpn-udp.service"
    assert journal_unit_name("evil") is None


def _local_adapter():
    service = MagicMock()
    warper = MagicMock()
    awg2 = MagicMock()
    return LocalNodeAdapter(service=service, warper=warper, awg2=awg2), service, awg2


@pytest.mark.skipif(sqlalchemy is None, reason="sqlalchemy not installed")
def test_local_node_adapter_sample_openvpn_journal_delegates(monkeypatch):
    adapter, _service, _awg2 = _local_adapter()
    calls: list[tuple[str, int]] = []

    def fake_fetch(unit: str, window_seconds: int) -> dict:
        calls.append((unit, window_seconds))
        return {"ok": True, "unit": "vpn-udp", "text": "log\n", "error": None}

    monkeypatch.setattr("app.services.node_adapter.fetch_unit_journal", fake_fetch)

    result = adapter.sample_openvpn_journal("openvpn-server@vpn-udp", 60)
    assert result["ok"] is True
    assert calls == [("openvpn-server@vpn-udp", 60)]


@pytest.mark.skipif(sqlalchemy is None, reason="sqlalchemy not installed")
def test_remote_node_adapter_sample_openvpn_journal_hits_expected_route(monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    request_calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        request_calls.append((method, path, kwargs))
        return {"ok": True, "unit": "vpn-udp", "text": "log\n", "error": None}

    monkeypatch.setattr(adapter, "_request", fake_request)

    result = adapter.sample_openvpn_journal("vpn-udp", 120)
    assert result["ok"] is True
    assert request_calls == [
        (
            "POST",
            "/openvpn/buffer-guard/journal-sample",
            {"json": {"unit": "vpn-udp", "window_seconds": 120}, "timeout": 60.0},
        )
    ]

