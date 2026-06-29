"""Security headers, crawl policy, and well-known files for the admin panel."""

from __future__ import annotations

import re
import secrets
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


def generate_csp_nonce() -> str:
    return secrets.token_urlsafe(16)


def apply_csp_nonce(base_csp: str, nonce: str | None, *, relaxed: bool = False) -> str:
    if not nonce or relaxed:
        return base_csp

    def _patch_script_src(match: re.Match[str]) -> str:
        directive = match.group(1)
        directive = directive.replace("'unsafe-inline'", "")
        directive = re.sub(r"\s+", " ", directive).strip()
        nonce_token = f"'nonce-{nonce}'"
        if nonce_token not in directive:
            directive = f"{directive} {nonce_token}".strip()
        return f"script-src {directive};"

    def _patch_style_src(match: re.Match[str]) -> str:
        directive = match.group(1)
        directive = directive.replace("'unsafe-inline'", "")
        directive = re.sub(r"\s+", " ", directive).strip()
        nonce_token = f"'nonce-{nonce}'"
        if nonce_token not in directive:
            directive = f"{directive} {nonce_token}".strip()
        return f"style-src {directive};"

    csp = re.sub(r"script-src\s+([^;]+);", _patch_script_src, base_csp, count=1)
    if re.search(r"style-src\s+[^;]+;", csp):
        csp = re.sub(r"style-src\s+([^;]+);", _patch_style_src, csp, count=1)
    return csp


def csp_for_path(path: str, base_csp: str, nonce: str | None = None, *, relaxed: bool = False) -> str:
    if is_tg_mini_path(path):
        # telegram-web-app.js initializes via inline scripts; CSP nonces break initData in WebView.
        csp = base_csp
        stripped = re.sub(r"frame-ancestors[^;]*;?\s*", "", csp).strip()
        if stripped and not stripped.endswith(";"):
            stripped += ";"

        def _patch_script_src(match: re.Match[str]) -> str:
            directive = match.group(1)
            if "'unsafe-inline'" not in directive:
                directive = f"{directive} 'unsafe-inline'".strip()
            return f"script-src {directive};"

        stripped = re.sub(r"script-src\s+([^;]+);", _patch_script_src, stripped, count=1)
        return f"{stripped} {TG_MINI_FRAME_ANCESTORS};".strip()

    csp = apply_csp_nonce(base_csp, nonce, relaxed=relaxed)
    return csp


class HttpSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        request.state.csp_nonce = generate_csp_nonce()

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
            nonce = getattr(request.state, "csp_nonce", None) if request is not None else None
            csp = csp_for_path(
                path,
                settings.content_security_policy,
                nonce,
                relaxed=settings.csp_relaxed_dev,
            )
            response.headers["Content-Security-Policy"] = csp
        if should_noindex_path(path):
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
