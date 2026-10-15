"""The Mini App page must load: the panel settings are not the tg_mini.settings submodule."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import tg_mini


def test_mini_app_page_loads(tmp_path, monkeypatch):
    index = tmp_path / "tg-mini.html"
    index.write_text("<html><head></head><body></body></html>", encoding="utf-8")
    monkeypatch.setattr(tg_mini, "_static_index", lambda: index)
    app = FastAPI()
    app.include_router(tg_mini.router, prefix="/api")

    response = TestClient(app).get("/api/tg-mini")

    assert response.status_code == 200
