"""HTTP security middleware tests (adapted from AdminAntizapret test_http_security)."""

from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.middleware.http_security import (
    HttpSecurityMiddleware,
    apply_csp_nonce,
    build_robots_txt,
    build_security_txt,
    csp_for_path,
    get_panel_branding,
    is_tg_mini_path,
    should_noindex_path,
)
from app.services.html_csp import CSP_NONCE_PLACEHOLDER, inject_csp_nonce
from tests.conftest import run_async


def test_should_noindex_sensitive_paths():
    assert should_noindex_path("/")
    assert should_noindex_path("/settings")
    assert should_noindex_path("/routing")
    assert should_noindex_path("/server-monitor")
    assert should_noindex_path("/logs")
    assert should_noindex_path("/edit-files")
    assert should_noindex_path("/feature-disabled")
    assert should_noindex_path("/api/system-info")
    assert should_noindex_path("/login")
    assert should_noindex_path("/api/tg-mini/open")
    assert should_noindex_path("/api/public/qr-download/abc")
    assert should_noindex_path("/api/public/route-download/keenetic")


def test_apply_security_headers_sets_csp_and_noindex_for_login():
    response = type("R", (), {"headers": {}})()

    class H(dict):
        def setdefault(self, k, v):
            if k not in self:
                self[k] = v
            return self[k]

    response.headers = H()
    settings = Settings(content_security_policy="default-src 'self'")
    HttpSecurityMiddleware._apply_headers(response, settings, "/login")
    assert "Content-Security-Policy" in response.headers
    assert response.headers.get("X-Robots-Tag") == "noindex, nofollow, noarchive"


def test_build_robots_txt_blocks_download_paths():
    body = build_robots_txt()
    assert "Disallow: /" in body
    assert "Disallow: /settings" in body
    assert "Disallow: /routing" in body
    assert "Disallow: /api/" in body
    assert "Disallow: /login" in body
    assert "Disallow: /api/public/qr-download/" in body
    assert "Disallow: /ip-blocked" in body


def test_build_security_txt_has_no_vpn_wording():
    body = build_security_txt({"panel_base_url": "https://panel.example.com"})
    assert "VPN" not in body
    assert "vpn" not in body
    assert "Private administration panel" in body
    assert "https://panel.example.com" in body


def test_get_panel_branding_uses_domain_only():
    branding = get_panel_branding(
        {
            "DOMAIN": "admin.example.com",
            "PANEL_BRAND_NAME": "",
        }
    )
    assert branding["panel_brand_name"] == "Admin Panel"
    assert branding["panel_host"] == "admin.example.com"
    assert branding["panel_base_url"] == "https://admin.example.com"


def test_robots_and_security_txt_routes():
    from app.main import app

    client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /api/" in robots.text

    security = client.get("/.well-known/security.txt")
    assert security.status_code == 200
    assert "Private administration panel" in security.text


def test_security_headers_on_health(async_client):
    response = run_async(async_client("GET", "/api/health"))
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert response.headers.get("Cross-Origin-Resource-Policy") == "same-origin"
    assert response.headers.get("Cross-Origin-Opener-Policy") is None
    assert "Content-Security-Policy" in response.headers
    assert response.headers.get("X-Robots-Tag") == "noindex, nofollow, noarchive"


def test_security_headers_disabled():
    from app.main import app

    disabled = Settings(security_headers_enabled=False)
    with patch("app.middleware.http_security.get_settings", return_value=disabled):
        transport = ASGITransport(app=app)

        async def _call():
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get("/api/health")

        response = run_async(_call())
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") is None


def test_enforce_https_redirect():
    from app.main import app

    settings = Settings(enforce_https=True, security_headers_enabled=False, api_rate_limit_enabled=False)
    transport = ASGITransport(app=app)

    async def _call():
        with patch("app.middleware.http_security.get_settings", return_value=settings):
            with patch("app.services.api_rate_limit.get_settings", return_value=settings):
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    return await client.get("/api/health", follow_redirects=False)

    response = run_async(_call())
    assert response.status_code == 308
    assert response.headers["location"].startswith("https://")


def test_middleware_is_secure_with_forwarded_proto():
    class FakeRequest:
        url = type("U", (), {"scheme": "http"})()
        headers = {"x-forwarded-proto": "https"}

    assert HttpSecurityMiddleware._is_secure(FakeRequest()) is True


def test_middleware_apply_headers_sets_csp():
    class Response:
        def __init__(self):
            self.headers = {}

    response = Response()
    settings = Settings(content_security_policy="default-src 'self'; frame-ancestors 'self';")
    HttpSecurityMiddleware._apply_headers(response, settings, "/api/health")
    assert response.headers.get("Content-Security-Policy") == "default-src 'self'; frame-ancestors 'self';"


def test_tg_mini_path_allows_telegram_frame_ancestors():
    base = (
        "default-src 'self'; script-src 'self' https://telegram.org; "
        "frame-ancestors 'self'; base-uri 'self';"
    )
    csp = csp_for_path("/api/tg-mini", base)
    assert "https://web.telegram.org" in csp
    assert "frame-ancestors 'self'" not in csp or "https://telegram.org" in csp


def test_tg_mini_path_skips_x_frame_options():
    class Response:
        def __init__(self):
            self.headers = {}

    response = Response()
    settings = Settings(content_security_policy="default-src 'self'; frame-ancestors 'self';")
    HttpSecurityMiddleware._apply_headers(response, settings, "/api/tg-mini")
    assert response.headers.get("X-Frame-Options") is None
    assert is_tg_mini_path("/api/tg-mini/assets/app.js")


def test_apply_csp_nonce_removes_unsafe_inline_from_script_src():
    base = (
        "default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; "
        "style-src 'self'; style-src-attr 'unsafe-inline';"
    )
    csp = apply_csp_nonce(base, "abc123")
    assert "'unsafe-inline'" not in csp.split("style-src")[0]
    assert "'nonce-abc123'" in csp
    assert "style-src 'self' 'nonce-abc123'" in csp
    assert "style-src-attr 'unsafe-inline'" in csp
    assert "'unsafe-inline'" not in csp.split("style-src-attr")[0]


def test_csp_for_path_with_nonce_on_tg_mini():
    base = (
        "default-src 'self'; script-src 'self' https://telegram.org; "
        "frame-ancestors 'self';"
    )
    csp = csp_for_path("/api/tg-mini", base, "nonce-test")
    assert "'nonce-nonce-test'" in csp
    assert "'unsafe-inline'" not in csp.split("style-src")[0] if "style-src" in csp else True
    assert "https://web.telegram.org" in csp


def test_inject_csp_nonce_replaces_placeholder_and_adds_to_scripts():
    html = f'<html><script nonce="{CSP_NONCE_PLACEHOLDER}" src="/app.js"></script></html>'
    out = inject_csp_nonce(html, "n1")
    assert CSP_NONCE_PLACEHOLDER not in out
    assert 'nonce="n1"' in out


def test_spa_index_served_with_matching_csp_nonce(tmp_path):
    from fastapi import FastAPI, Request
    from starlette.middleware.base import BaseHTTPMiddleware

    from app.middleware.http_security import HttpSecurityMiddleware
    from app.services.html_csp import serve_html_with_nonce

    dist = tmp_path / "dist"
    dist.mkdir()
    index = dist / "index.html"
    index.write_text(
        f'<html><body><script nonce="{CSP_NONCE_PLACEHOLDER}" src="/assets/app.js"></script></body></html>',
        encoding="utf-8",
    )

    app = FastAPI()
    app.add_middleware(HttpSecurityMiddleware)

    @app.get("/")
    async def root(request: Request):
        return serve_html_with_nonce(request, index)

    client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    csp = response.headers.get("Content-Security-Policy", "")
    assert "'unsafe-inline'" not in csp.split("style-src")[0] if "style-src" in csp else True
    nonce_match = __import__("re").search(r"'nonce-([^']+)'", csp)
    assert nonce_match is not None
    nonce = nonce_match.group(1)
    assert f'nonce="{nonce}"' in response.text
    assert CSP_NONCE_PLACEHOLDER not in response.text
