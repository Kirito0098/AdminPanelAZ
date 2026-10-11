"""/assets: login-only JS chunks look missing to anonymous visitors; signed-in browsers get them uncached by CDNs."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import get_settings
from app.services import frontend_assets
from app.services.asset_marker import ASSET_MARKER_COOKIE, issue_asset_marker

MANIFEST = {
    "index.html": {
        "file": "assets/entry.js",
        "isEntry": True,
        "imports": ["_shared.js"],
        "dynamicImports": ["_shell.js", "src/pages/PortalPage.tsx"],
        "css": ["assets/style.css"],
    },
    "_shared.js": {"file": "assets/shared.js"},
    "src/pages/PortalPage.tsx": {"file": "assets/portal.js", "imports": ["index.html", "_shared.js"]},
    "_shell.js": {
        "file": "assets/shell.js",
        "name": "AppShell",
        "imports": ["index.html"],
        "dynamicImports": ["src/pages/SettingsPage.tsx"],
    },
    "src/pages/SettingsPage.tsx": {"file": "assets/page.js", "imports": ["_shell.js"]},
}


def _write_build(dist: Path, manifest: dict | None = MANIFEST) -> None:
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")
    for name in ("entry.js", "shared.js", "portal.js", "shell.js", "page.js"):
        (dist / "assets" / name).write_text(f"/* {name.upper()} */", encoding="utf-8")
    (dist / "assets" / "style.css").write_text("body{}", encoding="utf-8")
    if manifest is not None:
        (dist / ".vite").mkdir()
        (dist / ".vite" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dist = tmp_path / "dist"
    _write_build(dist)
    monkeypatch.setattr(main_module.settings, "frontend_dist_path", dist)
    monkeypatch.setattr(main_module, "_ACCESS_PREFIX", "")
    monkeypatch.setattr(
        "app.services.html_csp.serve_html_with_nonce",
        lambda request, index_file, portal_root=False: PlainTextResponse("INDEX"),
    )
    return dist


def _client(marker: str | None = None) -> TestClient:
    app = FastAPI()
    main_module._mount_frontend(app)
    client = TestClient(app)
    if marker is not None:
        client.cookies.set(ASSET_MARKER_COOKIE, marker)
    return client


def _marker() -> str:
    return issue_asset_marker(get_settings().secret_key, 600)


@pytest.mark.parametrize("name", ["entry.js", "shared.js", "portal.js", "style.css"])
def test_anonymous_visitor_gets_login_and_portal_files(dist: Path, name: str):
    response = _client().get(f"/assets/{name}")

    assert response.status_code == 200
    assert "cache-control" not in response.headers


@pytest.mark.parametrize("name", ["shell.js", "page.js"])
def test_login_only_chunk_looks_missing_to_anonymous_visitor(dist: Path, name: str):
    client = _client()

    gated = client.get(f"/assets/{name}")
    missing = client.get("/assets/nope.js")

    assert gated.status_code == missing.status_code == 404
    assert gated.text == missing.text
    assert gated.headers["cache-control"] == missing.headers["cache-control"] == "no-store"
    assert name.upper() not in gated.text


def test_head_request_is_gated_too(dist: Path):
    assert _client().head("/assets/shell.js").status_code == 404


def test_signed_in_browser_gets_login_only_chunk_that_shared_caches_keep_out(dist: Path):
    response = _client(_marker()).get("/assets/shell.js")

    assert response.status_code == 200
    assert "SHELL.JS" in response.text
    assert response.headers["cache-control"] == "private, no-cache"
    assert response.headers["vary"] == "Cookie"


@pytest.mark.parametrize(
    "marker",
    ["", "garbage", issue_asset_marker("another-secret-key-0123456789abcdef", 600)],
)
def test_invalid_marker_counts_as_anonymous(dist: Path, marker: str):
    assert _client(marker).get("/assets/shell.js").status_code == 404


def test_expired_marker_counts_as_anonymous(dist: Path):
    expired = issue_asset_marker(get_settings().secret_key, 60, now=1_000_000)

    assert _client(expired).get("/assets/shell.js").status_code == 404


def test_build_without_manifest_stays_fully_public(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dist = tmp_path / "dist"
    _write_build(dist, manifest=None)
    monkeypatch.setattr(main_module.settings, "frontend_dist_path", dist)
    monkeypatch.setattr(main_module, "_ACCESS_PREFIX", "")

    assert _client().get("/assets/shell.js").status_code == 200


def test_rebuilt_frontend_is_picked_up_without_restart(dist: Path):
    client = _client()
    assert client.get("/assets/shell.js").status_code == 404

    dist.rename(dist.with_name("dist.old"))
    _write_build(dist, {**MANIFEST, "index.html": {**MANIFEST["index.html"], "imports": ["_shared.js", "_shell.js"]}})

    assert client.get("/assets/shell.js").status_code == 200


def test_spa_fallback_does_not_serve_a_login_only_chunk(dist: Path):
    response = _client().get("/foo%2f..%2fassets%2fshell.js")

    assert "SHELL.JS" not in response.text


def test_access_path_mount_and_portal_root_mount_are_both_gated(dist: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module, "_ACCESS_PREFIX", "/panel")
    client = _client()

    assert client.get("/assets/portal.js").status_code == 200
    assert client.get("/panel/assets/portal.js").status_code == 200
    assert client.get("/assets/shell.js").status_code == 404
    assert client.get("/panel/assets/shell.js").status_code == 404

    client.cookies.set(ASSET_MARKER_COOKIE, _marker())

    assert client.get("/panel/assets/shell.js").status_code == 200


def test_public_roots_match_the_bundle_check():
    script = Path(__file__).resolve().parents[2] / "frontend" / "scripts" / "check-entry-chunks.mjs"
    match = re.search(r"const PUBLIC_ROOTS = \[([^\]]*)\]", script.read_text(encoding="utf-8"))

    assert match
    assert tuple(re.findall(r"'([^']+)'", match.group(1))) == frontend_assets.PUBLIC_ROOTS
