"""Gate non-portal paths when Host matches configured portal_domain."""

from __future__ import annotations

import time

_CACHE_TTL_SEC = 30.0
_cached_portal_host: str | None = None
_cached_at_monotonic: float = 0.0


def normalize_request_host(host_header: str | None) -> str:
    host = (host_header or "").split(",")[0].strip().lower()
    return host.split(":")[0].strip()


def is_portal_path_allowed(path: str) -> bool:
    """Paths served on the dedicated portal host (everything else → 404)."""
    p = path or "/"
    if p == "/p" or p.startswith("/p/"):
        return True
    if p.startswith("/api/public/"):
        return True
    if p == "/assets" or p.startswith("/assets/"):
        return True
    return False


def invalidate_portal_domain_cache() -> None:
    global _cached_portal_host, _cached_at_monotonic
    _cached_portal_host = None
    _cached_at_monotonic = 0.0


def get_cached_portal_domain(*, force_refresh: bool = False) -> str:
    """Portal host from DB with a short TTL cache (empty string is cached too)."""
    global _cached_portal_host, _cached_at_monotonic
    now = time.monotonic()
    if (
        not force_refresh
        and _cached_portal_host is not None
        and (now - _cached_at_monotonic) < _CACHE_TTL_SEC
    ):
        return _cached_portal_host

    from app.database import SessionLocal
    from app.services.client_portal import get_portal_domain

    db = SessionLocal()
    try:
        host = (get_portal_domain(db) or "").strip().lower()
    finally:
        db.close()
    _cached_portal_host = host
    _cached_at_monotonic = now
    return host
