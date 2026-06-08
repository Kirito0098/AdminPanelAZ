"""Human-readable remaining VPN client access time (ported from AdminAntizapret)."""

from __future__ import annotations

from datetime import datetime, timezone

_EXPIRES_AT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M UTC",
)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_expires_at(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    text = str(value).strip()
    if not text:
        return None
    for fmt in _EXPIRES_AT_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def is_access_expired(expires_at, *, now=None):
    """Return True if access expired, False if still valid, None if unknown."""
    expires_dt = _parse_expires_at(expires_at)
    if expires_dt is None:
        return None

    now_dt = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    return _as_utc(expires_dt) <= now_dt


def format_access_remaining(expires_at, *, now=None):
    """Return human-readable remaining access time or None if unknown."""
    expires_dt = _parse_expires_at(expires_at)
    if expires_dt is None:
        return None

    now_dt = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    delta = _as_utc(expires_dt) - now_dt
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "срок истёк"

    days = delta.days
    if days >= 1:
        return f"{days} дн."

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0 and minutes > 0:
        return f"{hours} ч. {minutes} мин."
    if hours > 0:
        return f"{hours} ч."
    if minutes > 0:
        return f"{minutes} мин."
    return "менее минуты"
