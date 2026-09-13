"""Portal routes remain at domain root when panel ACCESS_PATH is set."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import public_portal as public_portal_router
from app.services import html_csp


def test_rewrite_relative_asset_urls_force_root_ignores_access_path():
    html = '<script src="./assets/index.js"></script>'
    settings = MagicMock()
    settings.access_path = "/panel"
    out = html_csp.rewrite_relative_asset_urls(html, settings, force_root=True)
    assert '"/assets/index.js"' in out
    assert "/panel/assets" not in out


def test_serve_html_portal_root_omits_access_path_script(tmp_path: Path):
    index = tmp_path / "index.html"
    index.write_text(
        "<!DOCTYPE html><html><head><title>t</title></head><body></body></html>",
        encoding="utf-8",
    )
    request = MagicMock()
    request.state.csp_nonce = "n"
    with patch("app.services.html_csp.get_settings") as gs:
        gs.return_value.access_path = "/panel"
        response = html_csp.serve_html_with_nonce(request, index, portal_root=True)
    body = response.body.decode("utf-8")
    assert "__PANEL_ACCESS_PATH__" not in body
    assert "/panel/assets" not in body


def test_public_portal_api_available_at_root_and_prefixed():
    app = FastAPI()
    app.include_router(public_portal_router.router, prefix="/panel/api")
    app.include_router(public_portal_router.router, prefix="/api")

    token_row = MagicMock()
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host"),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service"),
        patch("app.routers.public_portal.get_valid_portal_token", return_value=token_row),
        patch(
            "app.routers.public_portal.build_portal_payload",
            return_value={"client_name": "alice", "files": []},
        ),
    ):
        feats.return_value.is_enabled.return_value = True
        ip_svc.get_client_ip.return_value = "1.2.3.4"
        with TestClient(app) as client:
            root = client.get("/api/public/portal/tok")
            prefixed = client.get("/panel/api/public/portal/tok")

    assert root.status_code == 200
    assert prefixed.status_code == 200
    assert root.json()["client_name"] == "alice"
    assert prefixed.json()["client_name"] == "alice"
