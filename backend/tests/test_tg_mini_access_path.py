from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.routers import tg_mini as tg_mini_router


def test_mini_app_page_injects_access_path(monkeypatch, tmp_path: Path):
    index = tmp_path / "index.html"
    index.write_text(
        "<!DOCTYPE html><html><head><title>t</title></head><body></body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(tg_mini_router, "_static_index", lambda: index)
    monkeypatch.setattr(tg_mini_router, "settings", Settings(access_path="/panel"))
    monkeypatch.setattr(
        "app.services.html_csp.get_request_csp_nonce",
        lambda _request: "test-nonce",
    )

    request = MagicMock()
    request.url.path = "/panel/api/tg-mini"
    response = tg_mini_router.mini_app_page(request)
    body = response.body.decode("utf-8")
    assert 'window.__PANEL_ACCESS_PATH__="/panel"' in body
    assert '"./assets/' not in body or "/panel/api/tg-mini/assets/" in body


def test_mini_app_page_omits_access_path_when_empty(monkeypatch, tmp_path: Path):
    index = tmp_path / "index.html"
    index.write_text(
        "<!DOCTYPE html><html><head><title>t</title></head><body></body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(tg_mini_router, "_static_index", lambda: index)
    monkeypatch.setattr(tg_mini_router, "settings", Settings(access_path=""))
    monkeypatch.setattr(
        "app.services.html_csp.get_request_csp_nonce",
        lambda _request: "test-nonce",
    )

    request = MagicMock()
    request.url.path = "/api/tg-mini"
    response = tg_mini_router.mini_app_page(request)
    body = response.body.decode("utf-8")
    assert "__PANEL_ACCESS_PATH__" not in body


def test_mini_app_page_missing_index_returns_503(monkeypatch, tmp_path: Path):
    missing = tmp_path / "missing.html"
    monkeypatch.setattr(tg_mini_router, "_static_index", lambda: missing)
    with pytest.raises(HTTPException) as exc:
        tg_mini_router.mini_app_page(MagicMock(url=MagicMock(path="/api/tg-mini")))
    assert exc.value.status_code == 503
