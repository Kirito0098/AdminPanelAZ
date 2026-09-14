"""Portal domain suggestion, validation, and publish status helpers."""

from __future__ import annotations

import pytest

from app.services.client_portal import (
    assert_portal_domain_not_panel,
    normalize_portal_domain,
    suggest_portal_domain,
)
from app.services.panel_publish_info import build_portal_publish_status


def test_suggest_portal_domain_from_panel():
    assert suggest_portal_domain("example.com") == "portal.example.com"
    assert suggest_portal_domain("https://Panel.Example.com/") == "portal.example.com"
    assert suggest_portal_domain("admin.vpn.example.com") == "portal.vpn.example.com"
    assert suggest_portal_domain("portal.example.com") == "clients.example.com"
    assert suggest_portal_domain("") == ""
    assert suggest_portal_domain("not a host") == ""


def test_assert_portal_not_same_as_panel():
    with pytest.raises(ValueError, match="не должен совпадать"):
        assert_portal_domain_not_panel("example.com", "example.com")
    assert_portal_domain_not_panel("portal.example.com", "example.com")


def test_normalize_portal_domain_strips_scheme_port():
    assert normalize_portal_domain("https://Portal.Example.com:8443/x") == "portal.example.com"


def test_build_portal_publish_status_http_direct_unsupported():
    status = build_portal_publish_status(
        portal_domain="portal.example.com",
        panel_domain="example.com",
        publish_mode="http_direct",
        backend_port="5050",
    )
    assert status["suggested_portal_domain"] == "portal.example.com"
    assert status["portal_mode_supported"] is False
    assert status["portal_ready"] is False
    assert status["portal_access_url"] == ""
    assert any("Nginx" in w for w in status["warnings"])


def test_build_portal_publish_status_uvicorn_unsupported():
    status = build_portal_publish_status(
        portal_domain="portal.example.com",
        panel_domain="example.com",
        publish_mode="uvicorn_le",
        ssl_cert="/nonexistent.pem",
    )
    assert status["portal_mode_supported"] is False
    assert status["portal_ready"] is False


def test_portal_publish_mode_supported_helper():
    from app.services.panel_publish_info import portal_publish_mode_supported

    assert portal_publish_mode_supported("nginx_le") is True
    assert portal_publish_mode_supported("nginx_custom") is True
    assert portal_publish_mode_supported("http_direct") is False
    assert portal_publish_mode_supported("uvicorn_le") is False


def test_build_portal_publish_status_nginx_needs_vhost():
    status = build_portal_publish_status(
        portal_domain="portal.example.com",
        panel_domain="example.com",
        publish_mode="nginx_le",
    )
    assert status["portal_ready"] is False
    assert status["portal_vhost_ok"] is False
    assert status["dns_hint"]


def test_build_portal_publish_status_nginx_not_ready_when_nginx_t_fails(monkeypatch):
    monkeypatch.setattr(
        "app.services.panel_publish_info.nginx_has_vhost_for_domain",
        lambda _domain: True,
    )
    monkeypatch.setattr(
        "app.services.panel_publish_info.nginx_config_test_ok",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.services.panel_publish_info.nginx_ssl_cert_path_for_domain",
        lambda _domain: "/tmp/fullchain.pem",
    )
    monkeypatch.setattr(
        "app.services.panel_publish_info.cert_covers_hostname",
        lambda _cert, _host: True,
    )
    status = build_portal_publish_status(
        portal_domain="portal.example.com",
        panel_domain="panel.example.com",
        publish_mode="nginx_le",
        ssl_cert="/tmp/fullchain.pem",
    )
    assert status["portal_ready"] is False
    assert status["portal_vhost_ok"] is False
    assert any("Глобальный nginx -t" in w for w in status["warnings"])
    assert status["suggested_portal_domain"] == "portal.example.com"


def test_build_portal_publish_status_nginx_ready_when_nginx_t_ok(monkeypatch):
    monkeypatch.setattr(
        "app.services.panel_publish_info.nginx_has_vhost_for_domain",
        lambda _domain: True,
    )
    monkeypatch.setattr(
        "app.services.panel_publish_info.nginx_config_test_ok",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.panel_publish_info.nginx_ssl_cert_path_for_domain",
        lambda _domain: "/tmp/fullchain.pem",
    )
    monkeypatch.setattr(
        "app.services.panel_publish_info.cert_covers_hostname",
        lambda _cert, _host: True,
    )
    status = build_portal_publish_status(
        portal_domain="portal.example.com",
        panel_domain="panel.example.com",
        publish_mode="nginx_le",
        ssl_cert="/tmp/fullchain.pem",
    )
    assert status["portal_ready"] is True
    assert status["portal_vhost_ok"] is True
    assert status["portal_cert_ok"] is True
