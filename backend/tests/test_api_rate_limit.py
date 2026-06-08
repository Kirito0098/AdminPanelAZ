"""Global API rate limit middleware tests."""

from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.middleware.api_rate_limit import is_api_rate_limit_exempt
from app.services.api_rate_limit import ApiRateLimitService
from app.services.rate_limit.backends import MemoryRateLimitBackend
from app.services.rate_limit.sliding_window import SlidingWindowLimiter
from tests.conftest import run_async


def test_is_api_rate_limit_exempt():
    assert is_api_rate_limit_exempt("/api/health") is True
    assert is_api_rate_limit_exempt("/api/ip-blocked") is True
    assert is_api_rate_limit_exempt("/api/ip-blocked/ping") is True
    assert is_api_rate_limit_exempt("/assets/app.js") is True
    assert is_api_rate_limit_exempt("/api/auth/login") is False


def test_api_rate_limit_blocks_after_threshold():
    service = ApiRateLimitService()
    service._limiter = SlidingWindowLimiter(MemoryRateLimitBackend())
    settings = Settings(
        api_rate_limit_enabled=True,
        api_rate_limit_max_requests=3,
        api_rate_limit_window_seconds=60,
    )
    with patch("app.services.api_rate_limit.get_settings", return_value=settings):
        service.consume("10.0.0.1")
        service.consume("10.0.0.1")
        service.consume("10.0.0.1")
        from app.services.rate_limit.sliding_window import RateLimitExceeded
        import pytest

        with pytest.raises(RateLimitExceeded) as exc:
            service.consume("10.0.0.1")
        assert exc.value.status_code == 429
        assert exc.value.headers.get("Retry-After") == "60"


def test_api_rate_limit_middleware_returns_429():
    from app.main import app

    settings = Settings(
        api_rate_limit_enabled=True,
        api_rate_limit_max_requests=2,
        api_rate_limit_window_seconds=60,
        security_headers_enabled=False,
    )
    service = ApiRateLimitService()
    service._limiter = SlidingWindowLimiter(MemoryRateLimitBackend())

    transport = ASGITransport(app=app)

    async def _call():
        with patch("app.services.api_rate_limit.get_settings", return_value=settings):
            with patch("app.services.api_rate_limit.api_rate_limit_service", service):
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    first = await client.get("/api/auth/captcha/required")
                    second = await client.get("/api/auth/captcha/required")
                    third = await client.get("/api/auth/captcha/required")
                    health = await client.get("/api/health")
                    return first, second, third, health

    first, second, third, health = run_async(_call())
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.headers.get("Retry-After") == "60"
    assert health.status_code == 200
