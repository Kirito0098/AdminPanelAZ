"""Static UI handlers for Telegram Mini App.

The entry bundle (shell, navigation, configs screen) is public: the Mini App has to
render before it can sign in with Telegram. Everything else — admin and extra screens
shipped as lazy chunks — is served only to a browser that already signed in, so an
anonymous visitor cannot read those screens out of the bundle. CSS stays public:
Tailwind classes are not a secret and the shell renders before sign-in.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from fastapi.responses import FileResponse

from app.config import get_settings
from app.services.frontend_assets import index_public_asset_names
from app.services.tg_mini_asset_marker import TG_MINI_ASSET_COOKIE, tg_mini_asset_marker_valid

_NOT_FOUND_HEADERS = {"Cache-Control": "no-store"}


def _public_js_names() -> frozenset[str]:
    """Chunks reachable from index.html by static imports; empty when index.html is missing."""
    from app.routers import tg_mini as root

    return index_public_asset_names(root._STATIC_DIR)


def mini_app_asset(file_path: str, request: Request):
    from app.routers import tg_mini as root

    assets_root = (root._STATIC_DIR / "assets").resolve()
    asset_path = (assets_root / file_path).resolve()
    if not asset_path.is_relative_to(assets_root) or not asset_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, headers=_NOT_FOUND_HEADERS)

    name = asset_path.relative_to(assets_root).as_posix()
    if asset_path.suffix != ".js" or name in _public_js_names():
        return FileResponse(asset_path)

    marker = request.cookies.get(TG_MINI_ASSET_COOKIE)
    if not tg_mini_asset_marker_valid(get_settings().secret_key, marker):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, headers=_NOT_FOUND_HEADERS)
    response = FileResponse(asset_path)
    response.headers["Cache-Control"] = "private, no-cache"
    response.headers["Vary"] = "Cookie"
    return response


def mini_app_page(request: Request):
    from fastapi.responses import HTMLResponse

    from app.routers import tg_mini as root
    from app.services.html_csp import get_request_csp_nonce, inject_csp_nonce
    from app.services.panel_paths import panel_access_path_script

    index_path = root._static_index()
    if not index_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mini App UI не собран. Выполните: cd frontend && npm run build:tg-mini",
        )
    # The page lives at .../tg-mini (no trailing slash), so relative
    # "./assets/..." URLs resolve one level up and 404. Rewrite them to the
    # actual request path so assets load regardless of proxy prefix.
    base_path = request.url.path.rstrip("/")
    html = index_path.read_text(encoding="utf-8")
    html = html.replace('"./assets/', f'"{base_path}/assets/')
    runtime_config = panel_access_path_script(get_settings())
    if runtime_config and "</head>" in html:
        html = html.replace("</head>", f"    {runtime_config}\n  </head>", 1)
    nonce = get_request_csp_nonce(request)
    if not nonce:
        from app.middleware.http_security import generate_csp_nonce

        nonce = generate_csp_nonce()
    return HTMLResponse(
        inject_csp_nonce(html, nonce),
        media_type="text/html",
        # Telegram WebView кеширует index и после обновления Mini App
        # продолжает грузить старый бандл; хешированные ассеты не страдают.
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
