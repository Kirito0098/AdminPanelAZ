"""Static UI handlers for Telegram Mini App."""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from fastapi.responses import FileResponse


def mini_app_asset(file_path: str):
    from app.routers import tg_mini as root

    asset_path = (root._STATIC_DIR / "assets" / file_path).resolve()
    assets_root = (root._STATIC_DIR / "assets").resolve()
    if not str(asset_path).startswith(str(assets_root)) or not asset_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(asset_path)


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
    runtime_config = panel_access_path_script(root.settings)
    if runtime_config and "</head>" in html:
        html = html.replace("</head>", f"    {runtime_config}\n  </head>", 1)
    nonce = get_request_csp_nonce(request)
    if not nonce:
        from app.middleware.http_security import generate_csp_nonce

        nonce = generate_csp_nonce()
    return HTMLResponse(inject_csp_nonce(html, nonce), media_type="text/html")
