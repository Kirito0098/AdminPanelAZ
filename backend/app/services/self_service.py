"""Self-service quotas, create rate limits, and traffic scope for role=user."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, UserRole, VpnConfig
from app.services.app_setting_store import _get_setting, _set_setting
from app.services.rate_limit.backends import MemoryRateLimitBackend
from app.services.rate_limit.sliding_window import RateLimitExceeded, SlidingWindowLimiter
from app.services.user_subscription import user_subscription_expired

SETTING_QUOTA_DEFAULT = "user_config_quota_default"
SETTING_CREATE_RATE_MAX = "user_config_create_rate_max"
SETTING_CREATE_RATE_WINDOW = "user_config_create_rate_window_seconds"

DEFAULT_CONFIG_QUOTA = 5
DEFAULT_CREATE_RATE_MAX = 3
DEFAULT_CREATE_RATE_WINDOW_SECONDS = 3600

QUOTA_DEFAULT_BOUNDS = (0, 1000)
CREATE_RATE_MAX_BOUNDS = (0, 100)
CREATE_RATE_WINDOW_BOUNDS = (60, 86400)

REMINDER_DEDUP_SECONDS = 86400


def _get_setting_int(db: Session, key: str, default: int) -> int:
    raw = _get_setting(db, key, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def clamp_int(value: int, bounds: tuple[int, int]) -> int:
    low, high = bounds
    return max(low, min(high, int(value)))


def _get_bounded_int(db: Session, key: str, default: int, bounds: tuple[int, int]) -> int:
    return clamp_int(_get_setting_int(db, key, default), bounds)


def _quota_default(db: Session) -> int:
    return _get_bounded_int(db, SETTING_QUOTA_DEFAULT, DEFAULT_CONFIG_QUOTA, QUOTA_DEFAULT_BOUNDS)


def _create_rate_max(db: Session) -> int:
    return _get_bounded_int(db, SETTING_CREATE_RATE_MAX, DEFAULT_CREATE_RATE_MAX, CREATE_RATE_MAX_BOUNDS)


def _create_rate_window(db: Session) -> int:
    return _get_bounded_int(
        db, SETTING_CREATE_RATE_WINDOW, DEFAULT_CREATE_RATE_WINDOW_SECONDS, CREATE_RATE_WINDOW_BOUNDS
    )


def get_self_service_limits(db: Session) -> dict[str, int]:
    return {
        "quota_default": _quota_default(db),
        "create_rate_max": _create_rate_max(db),
        "create_rate_window_seconds": _create_rate_window(db),
    }


def set_self_service_limits(
    db: Session,
    *,
    quota_default: int | None = None,
    create_rate_max: int | None = None,
    create_rate_window_seconds: int | None = None,
) -> dict[str, int]:
    """Store limits (clamped). Caller commits."""
    if quota_default is not None:
        _set_setting(db, SETTING_QUOTA_DEFAULT, str(clamp_int(quota_default, QUOTA_DEFAULT_BOUNDS)))
    if create_rate_max is not None:
        _set_setting(db, SETTING_CREATE_RATE_MAX, str(clamp_int(create_rate_max, CREATE_RATE_MAX_BOUNDS)))
    if create_rate_window_seconds is not None:
        _set_setting(
            db,
            SETTING_CREATE_RATE_WINDOW,
            str(clamp_int(create_rate_window_seconds, CREATE_RATE_WINDOW_BOUNDS)),
        )
    db.flush()
    return get_self_service_limits(db)


def get_user_config_quota_limit(db: Session, user: User) -> int | None:
    """Return max configs for user, or None if unlimited."""
    if user.role == UserRole.admin:
        return None
    if user.config_quota is not None:
        return None if user.config_quota <= 0 else user.config_quota
    default = _quota_default(db)
    return None if default <= 0 else default


def count_user_configs(db: Session, user_id: int) -> int:
    """Count logical configs for quota (dedupe same client_name+vpn_type across nodes)."""
    pairs = (
        db.query(VpnConfig.client_name, VpnConfig.vpn_type)
        .filter(
            VpnConfig.owner_id == user_id,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .distinct()
        .all()
    )
    return len(pairs)


def get_owned_client_names(db: Session, user: User, node_id: int | None = None) -> set[str]:
    query = db.query(VpnConfig.client_name).filter(
        VpnConfig.owner_id == user.id,
        VpnConfig.ha_primary_config_id.is_(None),
    )
    if node_id is not None:
        query = query.filter(VpnConfig.node_id == node_id)
    return {name for (name,) in query.all() if name}


def build_quota_payload(db: Session, user: User) -> dict:
    limit = get_user_config_quota_limit(db, user)
    used = count_user_configs(db, user.id)
    remaining = None if limit is None else max(0, limit - used)
    rate_max = _create_rate_max(db)
    rate_window = _create_rate_window(db)
    return {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "unlimited": limit is None,
        "can_create": bool(getattr(user, "can_create_configs", True)) and (limit is None or used < limit),
        "create_rate_max": rate_max if user.role == UserRole.user else None,
        "create_rate_window_seconds": rate_window if user.role == UserRole.user else None,
    }


class UserConfigCreateRateLimitService:
    def __init__(self) -> None:
        self._limiter = SlidingWindowLimiter(MemoryRateLimitBackend())

    def consume(self, db: Session, user_id: int) -> None:
        max_requests = _create_rate_max(db)
        if max_requests <= 0:
            return
        window = float(_create_rate_window(db))
        detail = "Превышен лимит создания конфигов. Повторите позже."
        try:
            self._limiter.consume(
                f"user-config-create:{user_id}",
                max_requests,
                window,
                detail=detail,
            )
        except RateLimitExceeded as exc:
            retry = exc.headers.get("Retry-After", "60")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Превышен лимит создания конфигов: повторите через {retry} с",
            ) from exc


user_config_create_rate_limit_service = UserConfigCreateRateLimitService()


def enforce_user_can_create_config(db: Session, user: User) -> None:
    if user.role == UserRole.admin:
        return
    if user_subscription_expired(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="subscription_expired: Срок подписки истёк",
        )
    if not bool(getattr(user, "can_create_configs", True)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Создание конфигураций отключено администратором")
    limit = get_user_config_quota_limit(db, user)
    if limit is not None:
        used = count_user_configs(db, user.id)
        if used >= limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Достигнут лимит конфигураций ({limit})",
            )
    user_config_create_rate_limit_service.consume(db, user.id)


def reminder_recently_sent(db: Session, user_id: int, reminder_type: str, dedup_key: str) -> bool:
    from datetime import datetime, timedelta

    from app.models import UserReminderLog

    cutoff = datetime.utcnow() - timedelta(seconds=REMINDER_DEDUP_SECONDS)
    row = (
        db.query(UserReminderLog)
        .filter(
            UserReminderLog.user_id == user_id,
            UserReminderLog.reminder_type == reminder_type,
            UserReminderLog.dedup_key == dedup_key,
            UserReminderLog.sent_at >= cutoff,
        )
        .first()
    )
    return row is not None


def record_reminder_sent(db: Session, user_id: int, reminder_type: str, dedup_key: str) -> None:
    from datetime import datetime

    from app.models import UserReminderLog

    row = (
        db.query(UserReminderLog)
        .filter(
            UserReminderLog.user_id == user_id,
            UserReminderLog.reminder_type == reminder_type,
            UserReminderLog.dedup_key == dedup_key,
        )
        .first()
    )
    if row:
        row.sent_at = datetime.utcnow()
    else:
        db.add(
            UserReminderLog(
                user_id=user_id,
                reminder_type=reminder_type,
                dedup_key=dedup_key,
                sent_at=datetime.utcnow(),
            )
        )
    db.commit()


def self_service_reminder_enabled() -> bool:
    return get_settings().self_service_reminder_enabled
