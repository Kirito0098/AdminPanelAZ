"""Serve built SPA HTML with per-request CSP nonce substitution."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.services.panel_paths import access_path, panel_access_path_script

CSP_NONCE_PLACEHOLDER = "%CSP_NONCE%"

_SCRIPT_TAG_RE = re.compile(
    r'(<script\b(?![^>]*\bnonce=)(?![^>]*\bsrc=["\']https?://)[^>]*)(>)',
    re.IGNORECASE,
)
_MODULEPRELOAD_RE = re.compile(
    r'(<link\b[^>]*\brel=["\']modulepreload["\'][^>]*)(>)',
    re.IGNORECASE,
)


def inject_csp_nonce(html: str, nonce: str) -> str:
    """Replace placeholder and ensure script/modulepreload tags carry the nonce."""
    html = html.replace(CSP_NONCE_PLACEHOLDER, nonce)

    def _add_nonce(match: re.Match[str]) -> str:
        return f'{match.group(1)} nonce="{nonce}"{match.group(2)}'

    html = _SCRIPT_TAG_RE.sub(_add_nonce, html)
    html = _MODULEPRELOAD_RE.sub(_add_nonce, html)
    def _replace_meta_nonce(match: re.Match[str]) -> str:
        return f"{match.group(1)}{nonce}{match.group(2)}"

    html = re.sub(
        r'(<meta\b[^>]*\bname=["\']csp-nonce["\'][^>]*\bcontent=["\'])[^"\']*(["\'])',
        _replace_meta_nonce,
        html,
        count=1,
        flags=re.IGNORECASE,
    )
    return html


def rewrite_relative_asset_urls(html: str, settings=None, *, force_root: bool = False) -> str:
    """Make Vite ``./assets/...`` URLs absolute so deep SPA refreshes keep working.

    With ``base: './'``, a refresh on ``/settings/personal`` would otherwise
    request ``/settings/assets/...`` (HTML MIME) and white-screen.

    ``force_root=True`` is for the client portal host (``/p/…``), which never
    uses panel ACCESS_PATH.
    """
    cfg = settings or get_settings()
    prefix = "" if force_root else access_path(cfg)
    assets_base = f"{prefix}/assets" if prefix else "/assets"
    html = html.replace('"./assets/', f'"{assets_base}/')
    html = html.replace("'./assets/", f"'{assets_base}/")
    return html


def get_request_csp_nonce(request: Request) -> str | None:
    return getattr(request.state, "csp_nonce", None)


def serve_html_with_nonce(
    request: Request,
    index_file: Path,
    *,
    portal_root: bool = False,
) -> HTMLResponse:
    nonce = get_request_csp_nonce(request)
    if not nonce:
        from app.middleware.http_security import generate_csp_nonce

        nonce = generate_csp_nonce()
    settings = get_settings()
    html = index_file.read_text(encoding="utf-8")
    html = rewrite_relative_asset_urls(html, settings, force_root=portal_root)
    # Portal pages on a dedicated host must call /api and /assets at root, even
    # when the admin panel is published under ACCESS_PATH (e.g. /panel).
    if not portal_root:
        script = panel_access_path_script(settings)
        if script and "</head>" in html:
            html = html.replace("</head>", f"    {script}\n  </head>", 1)
    # Never cache the SPA shell: after rebuild Vite hashes change and a stale
    # index.html points at deleted /assets/index-*.js → blank white page.
    return HTMLResponse(
        inject_csp_nonce(html, nonce),
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )
