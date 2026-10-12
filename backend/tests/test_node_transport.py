"""Tests for node transport registry."""

from __future__ import annotations

from app.services import node_transport as nt


def test_list_transports_marks_ssh_unavailable(monkeypatch):
    monkeypatch.setattr(nt, "is_node_ssh_transport_enabled", lambda _db=None: False)
    items = {i["id"]: i for i in nt.list_transports()}
    assert items["http"]["available"] is True
    assert items["mtls"]["available"] is True
    assert items["ssh"]["available"] is False


def test_list_transports_marks_ssh_available_when_toggle_enabled(monkeypatch):
    monkeypatch.setattr(nt, "is_node_ssh_transport_enabled", lambda _db=None: True)
    items = {i["id"]: i for i in nt.list_transports()}
    assert items["ssh"]["available"] is True


def test_get_transport_http_and_mtls():
    class N:
        transport = "http"
        mtls_enabled = False
        is_local = False

    assert nt.get_transport(N()).id == "http"
    n = N()
    n.transport = "mtls"
    assert nt.get_transport(n).is_tls is True


def test_get_transport_unknown_fails():
    class N:
        transport = "wire"
        is_local = False

    try:
        nt.get_transport(N())
        assert False, "expected error"
    except ValueError as e:
        assert "transport" in str(e).lower() or "wire" in str(e)


def test_get_transport_ssh_in_db_returns_ssh_transport():
    class N:
        transport = "ssh"
        is_local = False

    transport = nt.get_transport(N())
    assert transport.id == "ssh"
    assert transport.is_tls is False


def test_node_uses_tls_follows_transport():
    class N:
        transport = "mtls"
        is_local = False

    assert nt.node_uses_tls(N()) is True

    class Local:
        transport = "mtls"
        is_local = True

    assert nt.node_uses_tls(Local()) is False

    class Bad:
        transport = "wire"
        is_local = False

    assert nt.node_uses_tls(Bad()) is False


def test_resolve_empty_transport_matches_legacy_mtls_flag():
    class N:
        transport = ""
        mtls_enabled = True
        is_local = False

    assert nt.resolve_transport_id(N()) == "mtls"
    assert nt.get_transport(N()).is_tls is True


def test_resolve_transport_wins_over_stale_mtls_flag():
    class N:
        transport = "http"
        mtls_enabled = True
        is_local = False

    assert nt.resolve_transport_id(N()) == "http"
    assert nt.get_transport(N()).is_tls is False


def test_remote_adapter_defaults_to_http_not_global_flag(monkeypatch):
    from app.services.node_adapter import RemoteNodeAdapter
    from app.services import node_mtls

    monkeypatch.setattr(node_mtls, "node_agent_mtls_enabled", lambda: True)
    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32)
    assert adapter.base_url.startswith("http://")
    assert adapter._mtls_enabled is False
