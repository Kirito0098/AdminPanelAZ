"""Security headers, crawl policy, and well-known files for the admin panel."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.config import get_settings

NOINDEX_PATH_PREFIXES = (
    "/",
    "/login",
    "/settings",
    "/routing",
    "/antizapret",
    "/server-monitor",
    "/logs",
    "/edit-files",
    "/feature-disabled",
    "/tg-mini",
    "/api/public/qr-download/",
    "/api/public/route-download/",
    "/api/auth/",
    "/api/ip-blocked",
    "/ip-blocked",
    "/api/",
)


def should_noindex_path(path: str) -> bool:
    if not path:
        return False
    normalized = path.rstrip("/") or "/"
    for prefix in NOINDEX_PATH_PREFIXES:
        p = prefix.rstrip("/") or "/"
        if normalized == p or path.startswith(prefix):
            return True
    return False


def build_robots_txt() -> str:
    return """User-agent: *
Disallow: /
Disallow: /login
Disallow: /settings
Disallow: /routing
Disallow: /antizapret
Disallow: /server-monitor
Disallow: /logs
Disallow: /edit-files
Disallow: /feature-disabled
Disallow: /api/public/qr-download/
Disallow: /api/public/route-download/
Disallow: /api/auth/
Disallow: /ip-blocked
Disallow: /api/ip-blocked
Disallow: /tg-mini
Disallow: /api/
"""


def get_panel_branding(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    import os

    getter = environ if environ is not None else os.environ
    domain = (getter.get("DOMAIN", "") or "").strip()
    brand = (getter.get("PANEL_BRAND_NAME", "") or "").strip() or "Admin Panel"
    panel_base_url = None
    if domain:
        host = domain.split(":")[0]
        panel_base_url = f"https://{host}"
    return {
        "panel_brand_name": brand,
        "panel_host": domain or None,
        "panel_base_url": panel_base_url,
    }


def build_security_txt(branding: Mapping[str, Any] | None = None) -> str:
    info = dict(branding or get_panel_branding())
    panel_url = info.get("panel_base_url") or "https://localhost"
    return (
        f"Contact: {panel_url}\n"
        "Preferred-Languages: ru, en\n"
        f"Canonical: {panel_url}\n"
        "Policy: Private administration panel. Authorized access only. Not a bank or email login.\n"
    )


def is_tg_mini_path(path: str) -> bool:
    return path.startswith("/api/tg-mini")


TG_MINI_FRAME_ANCESTORS = (
    "frame-ancestors 'self' "
    "https://web.telegram.org https://weba.telegram.org https://webk.telegram.org "
    "https://telegram.org https://t.me"
)


def csp_for_path(path: str, base_csp: str) -> str:
    if not is_tg_mini_path(path):
        return base_csp
    stripped = re.sub(r"frame-ancestors[^;]*;?\s*", "", base_csp).strip()
    if stripped and not stripped.endswith(";"):
        stripped += ";"
    return f"{stripped} {TG_MINI_FRAME_ANCESTORS};".strip()


class HttpSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()

        if settings.enforce_https and not self._is_secure(request):
            url = str(request.url).replace("http://", "https://", 1)
            return RedirectResponse(url=url, status_code=308)

        response = await call_next(request)

        if settings.security_headers_enabled:
            self._apply_headers(response, settings, request.url.path or "", request)

        return response

    @staticmethod
    def _is_secure(request: Request) -> bool:
        if request.url.scheme == "https":
            return True
        proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        return proto == "https"

    @staticmethod
    def _apply_headers(response: Response, settings, path: str, request: Request | None = None) -> None:
        tg_mini = is_tg_mini_path(path)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if not tg_mini:
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if not tg_mini:
            response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if request is not None and HttpSecurityMiddleware._is_secure(request):
            coop = "same-origin-allow-popups" if path.rstrip("/") in ("/login", "") else "same-origin"
            response.headers.setdefault("Cross-Origin-Opener-Policy", coop)
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
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
            csp = csp_for_path(path, settings.content_security_policy)
            response.headers["Content-Security-Policy"] = csp
        if should_noindex_path(path):
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
