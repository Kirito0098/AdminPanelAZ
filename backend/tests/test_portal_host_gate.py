from unittest.mock import MagicMock, patch

from app.services.portal_host_gate import (
    get_cached_portal_domain,
    invalidate_portal_domain_cache,
    is_portal_path_allowed,
    normalize_request_host,
)


def test_normalize_request_host_strips_port_and_case():
    assert normalize_request_host("Portal.Example.COM:443") == "portal.example.com"
    assert normalize_request_host(None) == ""


def test_portal_path_allowlist():
    assert is_portal_path_allowed("/p/abc") is True
    assert is_portal_path_allowed("/p") is True
    assert is_portal_path_allowed("/api/public/portal/x") is True
    assert is_portal_path_allowed("/assets/index.js") is True
    assert is_portal_path_allowed("/assets") is True
    assert is_portal_path_allowed("/") is False
    assert is_portal_path_allowed("/login") is False
    assert is_portal_path_allowed("/password") is False
    assert is_portal_path_allowed("/panel") is False
    assert is_portal_path_allowed("/api/auth/login") is False
    assert is_portal_path_allowed("/api/telegram/webhook/x") is False


def test_get_cached_portal_domain_caches_and_invalidates():
    invalidate_portal_domain_cache()
    db = MagicMock()
    with patch("app.database.SessionLocal", return_value=db) as session_cls:
        with patch("app.services.client_portal.get_portal_domain", return_value="portal.example.com") as get_dom:
            assert get_cached_portal_domain() == "portal.example.com"
            assert get_cached_portal_domain() == "portal.example.com"
            assert get_dom.call_count == 1
            assert session_cls.call_count == 1
            db.close.assert_called()

            invalidate_portal_domain_cache()
            assert get_cached_portal_domain() == "portal.example.com"
            assert get_dom.call_count == 2
