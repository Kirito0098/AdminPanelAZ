"""Tests for node transport registry."""

from __future__ import annotations

from app.services import node_transport as nt


def test_list_transports_marks_ssh_unavailable():
    items = {i["id"]: i for i in nt.list_transports()}
    assert items["http"]["available"] is True
    assert items["mtls"]["available"] is True
    assert items["ssh"]["available"] is False


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


def test_get_transport_ssh_in_db_fails():
    class N:
        transport = "ssh"
        is_local = False

    try:
        nt.get_transport(N())
        assert False, "expected error"
    except ValueError as e:
        assert "ssh" in str(e).lower() or "transport" in str(e).lower()


def test_apply_transport_rejects_ssh():
    class N:
        transport = "http"
        mtls_enabled = False

    try:
        nt.apply_transport_value(N(), "ssh")
        assert False
    except ValueError as e:
        assert "not_implemented" in str(e) or "ssh" in str(e).lower()


def test_apply_transport_syncs_mtls_flag():
    class N:
        transport = "http"
        mtls_enabled = False

    n = N()
    nt.apply_transport_value(n, "mtls")
    assert n.transport == "mtls"
    assert n.mtls_enabled is True
    nt.apply_transport_value(n, "http")
    assert n.transport == "http"
    assert n.mtls_enabled is False


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
