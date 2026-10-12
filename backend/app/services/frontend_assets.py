"""Frontend build files under /assets: which ones anonymous visitors may download (per the Vite manifest)."""

from __future__ import annotations

import json
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.config import get_settings
from app.services.asset_marker import ASSET_MARKER_COOKIE, asset_marker_valid

# Same list as PUBLIC_ROOTS in frontend/scripts/check-entry-chunks.mjs (npm run check:bundle).
PUBLIC_ROOTS = ("index.html", "src/pages/PortalPage.tsx")
_NOT_FOUND_HEADERS = {"Cache-Control": "no-store"}
_manifest_cache: dict[Path, tuple[tuple[int, int, int], frozenset[str] | None]] = {}


def _public_closure(manifest: dict) -> frozenset[str]:
    names: set[str] = set()
    pending = list(PUBLIC_ROOTS)
    seen: set[str] = set()
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        entry = manifest.get(key)
        if not isinstance(entry, dict):
            continue
        for file in [entry.get("file"), *entry.get("css", []), *entry.get("assets", [])]:
            if isinstance(file, str) and file.startswith("assets/"):
                names.add(file.removeprefix("assets/"))
        pending.extend(entry.get("imports", []))
    return frozenset(names)


def public_asset_names(dist: Path) -> frozenset[str] | None:
    """Names under ``assets/`` anyone may download; ``None`` when the build has no usable manifest."""
    manifest_file = dist / ".vite" / "manifest.json"
    try:
        stat = manifest_file.stat()
    except OSError:
        return None
    version = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
    cached = _manifest_cache.get(manifest_file)
    if cached is not None and cached[0] == version:
        return cached[1]
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    names = _public_closure(manifest) if isinstance(manifest, dict) and "index.html" in manifest else None
    _manifest_cache[manifest_file] = (version, names)
    return names


class FrontendAssets(StaticFiles):
    """JS outside the login and portal pages goes only to browsers holding a valid asset marker."""

    def __init__(self, *, dist: Path) -> None:
        super().__init__(directory=dist / "assets")
        self._dist = dist

    async def get_response(self, path: str, scope: Scope) -> Response:
        public = public_asset_names(self._dist)
        if public is None or not path.endswith(".js") or path in public:
            return await self._file(path, scope)
        marker = Request(scope).cookies.get(ASSET_MARKER_COOKIE)
        if not asset_marker_valid(get_settings().secret_key, marker):
            raise HTTPException(status_code=404, headers=_NOT_FOUND_HEADERS)
        response = await self._file(path, scope)
        response.headers["Cache-Control"] = "private, no-cache"
        response.headers["Vary"] = "Cookie"
        return response

    async def _file(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                raise HTTPException(status_code=404, headers=_NOT_FOUND_HEADERS) from None
            raise
