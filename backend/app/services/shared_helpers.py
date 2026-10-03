"""Small helpers shared across services (imported under their old private names)."""

from __future__ import annotations

import os
from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_client_name(client_name: str) -> str:
    return (client_name or "").strip().lower()


def env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def parse_bool(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def is_resource_monitor_enabled() -> bool:
    """Runtime gate — MONITOR_ENABLED / resource_monitor can flip without restart."""
    from app.services.feature_guards import get_feature_service

    return get_feature_service().is_enabled("resource_monitor")
