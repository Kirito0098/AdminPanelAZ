"""Small helpers shared across services (imported under their old private names)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(dt: datetime | None, *, convert_aware: bool = True) -> datetime | None:
    """Naive is treated as UTC; aware is converted unless ``convert_aware=False``."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    if convert_aware:
        return dt.astimezone(timezone.utc)
    return dt


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


def read_kv_file(path: Path, *, errors: str | None = "replace") -> dict[str, str]:
    """KEY=VALUE lines of an env-style file; comments and blank lines are skipped."""
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for raw in path.read_text(encoding="utf-8", errors=errors).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def format_avg_peak(
    avg: float | None, peak: float | None, *, suffix: str = "%", empty: str = "—"
) -> str | None:
    """«avg / peak» label for resource rows; ``empty`` marks a missing value."""
    if avg is None and peak is None:
        return None
    avg_label = empty if avg is None else f"{avg:g}{suffix}"
    peak_label = empty if peak is None else f"{peak:g}{suffix}"
    return f"{avg_label} / {peak_label}"
