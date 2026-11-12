"""Mini App static assets must stay inside the assets directory."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routers import tg_mini as root
from app.routers.tg_mini.static import mini_app_asset


@pytest.fixture()
def static_dir(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("ok", encoding="utf-8")
    (tmp_path / "assets.bak").mkdir()
    (tmp_path / "assets.bak" / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(root, "_STATIC_DIR", tmp_path)
    return tmp_path


def test_asset_inside_assets_dir_is_served(static_dir):
    response = mini_app_asset("app.js")

    assert Path(response.path) == static_dir / "assets" / "app.js"


def test_sibling_directory_assets_bak_is_not_served(static_dir):
    with pytest.raises(HTTPException) as exc:
        mini_app_asset("../assets.bak/secret.txt")

    assert exc.value.status_code == 404
