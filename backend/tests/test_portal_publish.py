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
    assert suggest_portal_domain("https://Panel.Example.com/") == "portal.panel.example.com"
    assert suggest_portal_domain("portal.example.com") == "clients.example.com"
    assert suggest_portal_domain("") == ""
    assert suggest_portal_domain("not a host") == ""


def test_assert_portal_not_same_as_panel():
    with pytest.raises(ValueError, match="не должен совпадать"):
        assert_portal_domain_not_panel("example.com", "example.com")
    assert_portal_domain_not_panel("portal.example.com", "example.com")


def test_normalize_portal_domain_strips_scheme_port():
    assert normalize_portal_domain("https://Portal.Example.com:8443/x") == "portal.example.com"


def test_build_portal_publish_status_http_direct():
    status = build_portal_publish_status(
        portal_domain="portal.example.com",
        panel_domain="example.com",
        publish_mode="http_direct",
        backend_port="5050",
    )
    assert status["suggested_portal_domain"] == "portal.example.com"
    assert status["portal_ready"] is True
    assert "5050" in status["portal_access_url"]
    assert any("HTTP" in w or "TLS" in w for w in status["warnings"])


def test_build_portal_publish_status_nginx_needs_vhost():
    status = build_portal_publish_status(
        portal_domain="portal.example.com",
        panel_domain="example.com",
        publish_mode="nginx_le",
    )
    assert status["portal_ready"] is False
    assert status["portal_vhost_ok"] is False
    assert status["dns_hint"]
