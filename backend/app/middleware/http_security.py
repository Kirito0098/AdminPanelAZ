"""Security headers and optional HTTPS enforcement."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.config import get_settings


class HttpSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()

        if settings.enforce_https and not self._is_secure(request):
            url = str(request.url).replace("http://", "https://", 1)
            return RedirectResponse(url=url, status_code=308)

        response = await call_next(request)

        if settings.security_headers_enabled:
            self._apply_headers(response, settings)

        return response

    @staticmethod
    def _is_secure(request: Request) -> bool:
        if request.url.scheme == "https":
            return True
        proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        return proto == "https"

    @staticmethod
    def _apply_headers(response: Response, settings) -> None:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        if settings.is_production or settings.behind_nginx:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.hsts_max_age}; includeSubDomains",
            )
        if settings.content_security_policy:
            response.headers.setdefault("Content-Security-Policy", settings.content_security_policy)
