from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.services.notify_time import (
    _normalize_timezone_name,
    effective_user_timezone,
    get_client_timezone_from_request,
)


def resolve_chart_timezone(
    *,
    user: Any | None = None,
    request: Any | None = None,
    explicit: str | None = None,
) -> str:
    # NOTE: when `request` is not provided, do not fall back to any ambient
    # module-level request state; callers should pass an explicit request
    # context to resolve from headers.
    request_tz = get_client_timezone_from_request(request) if request is not None else None
    for candidate in (explicit, effective_user_timezone(user), request_tz):
        resolved = _normalize_timezone_name(candidate)
        if resolved:
            return resolved
    return "UTC"


def _as_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def naive_utc_to_local(dt: datetime, tz_name: str) -> datetime:
    tz = ZoneInfo(_normalize_timezone_name(tz_name) or "UTC")
    return _as_utc_aware(dt).astimezone(tz)


def local_bucket_start_as_utc_iso(local_dt: datetime, bucket: str) -> str:
    if local_dt.tzinfo is None:
        raise ValueError("local_dt must be timezone-aware")
    if bucket == "minute5":
        minute = (local_dt.minute // 5) * 5
        start_local = local_dt.replace(minute=minute, second=0, microsecond=0)
    elif bucket == "hour":
        start_local = local_dt.replace(minute=0, second=0, microsecond=0)
    elif bucket == "day":
        start_local = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif bucket == "month":
        start_local = local_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_local = local_dt.replace(minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
