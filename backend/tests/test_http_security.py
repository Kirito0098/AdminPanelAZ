"""HTTP security middleware tests (adapted from AdminAntizapret test_http_security)."""

from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.middleware.http_security import HttpSecurityMiddleware
from tests.conftest import run_async


def test_security_headers_on_health(async_client):
    response = run_async(async_client("GET", "/api/health"))
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in response.headers


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

    settings = Settings(enforce_https=True, security_headers_enabled=False)
    transport = ASGITransport(app=app)

    async def _call():
        with patch("app.middleware.http_security.get_settings", return_value=settings):
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
    settings = Settings(content_security_policy="default-src 'self'")
    HttpSecurityMiddleware._apply_headers(response, settings)
    assert response.headers.get("Content-Security-Policy") == "default-src 'self'"
