"""URL path prefix helpers for subpath deployment (e.g. /panel on a shared domain)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

_RESERVED_PREFIXES = frozenset(
    {
        "/api",
        "/assets",
        "/.well-known",
        "/metrics",
        "/robots.txt",
    }
)
_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class AccessPathError(ValueError):
    """Invalid ACCESS_PATH value."""


def normalize_access_path(raw: str | None) -> str:
    """Normalize ACCESS_PATH to '' or '/segment' (no trailing slash)."""
    if raw is None:
        return ""
    value = str(raw).strip()
    if not value or value == "/":
        return ""
    if not value.startswith("/"):
        value = f"/{value}"
    value = value.rstrip("/")
    if value == "/":
        return ""
    if ".." in value.split("/"):
        raise AccessPathError("ACCESS_PATH must not contain '..'")
    segments = [s for s in value.split("/") if s]
    if not segments:
        return ""
    for segment in segments:
        if not _SEGMENT_RE.match(segment):
            raise AccessPathError(
                f"Invalid ACCESS_PATH segment '{segment}': use letters, digits, underscore, hyphen"
            )
    normalized = "/" + "/".join(segments)
    for reserved in _RESERVED_PREFIXES:
        if normalized == reserved or normalized.startswith(f"{reserved}/"):
            raise AccessPathError(f"ACCESS_PATH '{normalized}' conflicts with reserved path {reserved}")
    return normalized


def access_path(settings: Settings) -> str:
    return normalize_access_path(getattr(settings, "access_path", "") or "")


def api_prefix(settings: Settings) -> str:
    prefix = access_path(settings)
    return f"{prefix}/api" if prefix else "/api"


def auth_cookie_path(settings: Settings) -> str:
    return f"{api_prefix(settings)}/auth"


def with_access_path(settings: Settings, path: str) -> str:
    """Join ACCESS_PATH with an absolute app path (e.g. '/login' -> '/panel/login')."""
    prefix = access_path(settings)
    if not path:
        return prefix or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if not prefix:
        return path
    if path == "/":
        return f"{prefix}/"
    return f"{prefix}{path}"


def append_access_path_to_url_root(url_root: str, settings: Settings) -> str:
    """Append ACCESS_PATH to a URL root like https://host/ -> https://host/panel/."""
    prefix = access_path(settings)
    if not prefix:
        return url_root
    base = url_root.rstrip("/")
    return f"{base}{prefix}/"


def panel_access_path_script(settings: Settings) -> str:
    """Inline script tag injected into index.html for frontend runtime config."""
    prefix = access_path(settings)
    if not prefix:
        return ""
    escaped = prefix.replace("\\", "\\\\").replace('"', '\\"')
    return f'<script>window.__PANEL_ACCESS_PATH__="{escaped}"</script>'


def strip_access_path(path: str, settings: Settings) -> str:
    """Remove ACCESS_PATH prefix so middleware can match canonical /api routes."""
    prefix = access_path(settings)
    if not prefix:
        return path
    if path == prefix or path == f"{prefix}/":
        return "/"
    if path.startswith(f"{prefix}/"):
        stripped = path[len(prefix) :]
        return stripped or "/"
    return path


def expand_paths_for_access(settings: Settings, paths: tuple[str, ...]) -> tuple[str, ...]:
    """Duplicate path prefixes with ACCESS_PATH for noindex / matching."""
    prefix = access_path(settings)
    if not prefix:
        return paths
    expanded: list[str] = []
    for path in paths:
        if path == "/":
            expanded.extend([prefix, f"{prefix}/"])
        else:
            expanded.append(with_access_path(settings, path))
    return tuple(expanded)


def is_api_path(path: str, settings: Settings) -> bool:
    api = api_prefix(settings)
    return path == api or path.startswith(f"{api}/")


def get_ip_blocked_paths(settings: Settings) -> set[str]:
    api = api_prefix(settings)
    return {
        with_access_path(settings, "/ip-blocked"),
        f"{api}/ip-blocked",
        f"{api}/ip-blocked/ping",
    }
