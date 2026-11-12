"""/assets on a build without .vite/manifest.json: fail-closed to the index.html closure."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import get_settings
from app.services.asset_marker import ASSET_MARKER_COOKIE, issue_asset_marker


def _write_build(dist: Path) -> None:
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<script type="module" crossorigin src="./assets/entry.js"></script>', encoding="utf-8"
    )
    # The entry statically imports shared.js and lazy-loads the shell and the portal page.
    (dist / "assets" / "entry.js").write_text(
        'const deps=["./shell.js","./portal.js"];import a from"./shared.js";'
        'const shell=()=>import("./shell.js"),portal=()=>import("./portal.js");',
        encoding="utf-8",
    )
    (dist / "assets" / "shared.js").write_text("export const a=1;", encoding="utf-8")
    for name in ("shell.js", "portal.js", "page.js"):
        (dist / "assets" / name).write_text(f"/* {name.upper()} */", encoding="utf-8")


@pytest.fixture
def dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dist = tmp_path / "dist"
    _write_build(dist)
    monkeypatch.setattr(main_module.settings, "frontend_dist_path", dist)
    monkeypatch.setattr(main_module, "_ACCESS_PREFIX", "")
    return dist


def _client(marker: str | None = None) -> TestClient:
    app = FastAPI()
    main_module._mount_frontend(app)
    client = TestClient(app)
    if marker is not None:
        client.cookies.set(ASSET_MARKER_COOKIE, marker)
    return client


@pytest.mark.parametrize("name", ["entry.js", "shared.js"])
def test_index_entry_and_its_static_imports_stay_public(dist: Path, name: str):
    assert _client().get(f"/assets/{name}").status_code == 200


@pytest.mark.parametrize("name", ["shell.js", "portal.js", "page.js"])
def test_lazy_chunks_look_missing_to_anonymous_visitor(dist: Path, name: str):
    client = _client()

    gated = client.get(f"/assets/{name}")

    assert gated.status_code == 404
    assert gated.headers["cache-control"] == "no-store"
    assert name.upper() not in gated.text


def test_signed_in_browser_still_gets_lazy_chunks_without_manifest(dist: Path):
    marker = issue_asset_marker(get_settings().secret_key, 600)

    response = _client(marker).get("/assets/shell.js")

    assert response.status_code == 200
    assert "SHELL.JS" in response.text
    assert response.headers["cache-control"] == "private, no-cache"
