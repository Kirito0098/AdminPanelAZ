"""Per-route and global API rate limit middleware."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.services.api_rate_limit import api_rate_limit_service
from app.services.ip_restriction import ip_restriction_service
from app.services.rate_limit.sliding_window import RateLimitExceeded

_EXEMPT_PREFIXES = (
    "/api/health",
    "/api/ip-blocked",
    "/api/routing",
    "/api/tasks",
    "/metrics",
)


def is_api_rate_limit_exempt(path: str) -> bool:
    if not path.startswith("/api/"):
        return True
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in _EXEMPT_PREFIXES)


class ApiRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if is_api_rate_limit_exempt(path):
            return await call_next(request)

        client_ip = ip_restriction_service.get_client_ip(request)
        try:
            api_rate_limit_service.consume(client_ip)
        except RateLimitExceeded as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=dict(exc.headers or {}),
            )
        return await call_next(request)
