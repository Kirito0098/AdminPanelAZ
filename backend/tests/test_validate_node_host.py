"""Tests for validate_node_host internal-IP guard."""

import ipaddress

import pytest
from fastapi import HTTPException

from app.services import node_manager


def test_rejects_ipv6_loopback_when_internal_disallowed(monkeypatch):
    monkeypatch.setattr(node_manager.settings, "allow_internal_nodes", False)
    with pytest.raises(HTTPException) as exc:
        node_manager.validate_node_host("::1")
    assert exc.value.status_code == 400
    assert "Внутренние" in exc.value.detail


def test_rejects_bracketed_ipv6_loopback(monkeypatch):
    monkeypatch.setattr(node_manager.settings, "allow_internal_nodes", False)
    with pytest.raises(HTTPException) as exc:
        node_manager.validate_node_host("[::1]")
    assert exc.value.status_code == 400


def test_rejects_127_when_internal_disallowed(monkeypatch):
    monkeypatch.setattr(node_manager.settings, "allow_internal_nodes", False)
    with pytest.raises(HTTPException) as exc:
        node_manager.validate_node_host("127.0.0.1")
    assert exc.value.status_code == 400


def test_rejects_localhost_name_when_resolve_fails(monkeypatch):
    monkeypatch.setattr(node_manager.settings, "allow_internal_nodes", False)

    def boom(_host, _port=None):
        raise node_manager.socket.gaierror(node_manager.socket.EAI_NONAME, "nodename")

    monkeypatch.setattr(node_manager.socket, "getaddrinfo", boom)
    with pytest.raises(HTTPException) as exc:
        node_manager.validate_node_host("localhost")
    assert "localhost" in exc.value.detail.lower()


def test_allows_public_ipv4(monkeypatch):
    monkeypatch.setattr(node_manager.settings, "allow_internal_nodes", False)
    assert node_manager.validate_node_host("8.8.8.8") == "8.8.8.8"


def test_allows_loopback_when_internal_allowed(monkeypatch):
    monkeypatch.setattr(node_manager.settings, "allow_internal_nodes", True)
    assert node_manager.validate_node_host("::1") == "::1"


def test_rejects_hostname_resolving_to_private(monkeypatch):
    monkeypatch.setattr(node_manager.settings, "allow_internal_nodes", False)

    def fake_getaddrinfo(host, _port=None):
        assert host == "lan.example"
        return [(None, None, None, None, ("192.168.1.10", 0))]

    monkeypatch.setattr(node_manager.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HTTPException) as exc:
        node_manager.validate_node_host("lan.example")
    assert exc.value.status_code == 400
    # sanity: address truly private
    assert ipaddress.ip_address("192.168.1.10").is_private
