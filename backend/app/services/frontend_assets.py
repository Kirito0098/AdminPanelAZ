"""Frontend build files under /assets: which ones anonymous visitors may download (per the Vite manifest).

The manifest lists the entry and portal chunks, so it is the only way to tell the public closure from
login-only chunks. Without it the gate is fail-closed: anonymous visitors get ``index.html`` and the
chunks it statically imports (the login entry), everything else under ``/assets`` looks missing.
"""

from __future__ import annotations

import json
import re
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
# Chunks referenced by index.html (entry script, modulepreloads) — names under assets/.
_INDEX_ASSET_RE = re.compile(r"""(?:src|href)\s*=\s*["']\.?/?assets/([^"']+\.js)["']""")
# Static imports of a built chunk. Dynamic import("./x.js") is deliberately not matched: lazy routes
# (AppShell, panel pages, the portal) must stay login-only when the manifest cannot classify them.
_STATIC_IMPORT_RE = re.compile(r"""(?:from|import)(?!\s*\()\s*["']\./([^"']+\.js)["']""")
_manifest_cache: dict[Path, tuple[tuple[int, int, int], frozenset[str] | None]] = {}
_index_cache: dict[Path, tuple[tuple[int, int, int], frozenset[str]]] = {}


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


def index_public_asset_names(dist: Path) -> frozenset[str]:
    """Fail-closed fallback without the manifest: index.html and the chunks it imports statically."""
    index_file = dist / "index.html"
    try:
        stat = index_file.stat()
    except OSError:
        return frozenset()
    version = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
    cached = _index_cache.get(dist)
    if cached is not None and cached[0] == version:
        return cached[1]
    names = _index_closure(dist, _read_text(index_file))
    _index_cache[dist] = (version, names)
    return names


def _index_closure(dist: Path, html: str) -> frozenset[str]:
    names: set[str] = set()
    pending = list(_INDEX_ASSET_RE.findall(html))
    while pending:
        name = pending.pop()
        if name in names or not name.endswith(".js") or "/" in name or "\\" in name:
            continue
        names.add(name)
        pending.extend(_STATIC_IMPORT_RE.findall(_read_text(dist / "assets" / name)))
    return frozenset(names)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


class FrontendAssets(StaticFiles):
    """JS outside the login and portal pages goes only to browsers holding a valid asset marker."""

    def __init__(self, *, dist: Path) -> None:
        super().__init__(directory=dist / "assets")
        self._dist = dist

    async def get_response(self, path: str, scope: Scope) -> Response:
        public = public_asset_names(self._dist)
        if public is None:
            # Fail-closed: an old or broken build hides every lazy chunk instead of leaking the panel.
            public = index_public_asset_names(self._dist)
        if not path.endswith(".js") or path in public:
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
