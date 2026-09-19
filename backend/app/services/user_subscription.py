from __future__ import annotations

from datetime import datetime, timezone

from app.models import User


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_db_datetime(dt: datetime | None) -> datetime | None:
    value = _as_utc(dt)
    if value is None:
        return None
    return value.replace(tzinfo=None)


def get_user_access_until(user: User) -> datetime | None:
    return _as_utc(getattr(user, "access_until", None))


def user_subscription_expired(user: User, *, now: datetime | None = None) -> bool:
    deadline = get_user_access_until(user)
    if deadline is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return deadline <= current
