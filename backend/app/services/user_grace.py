"""Inactive-user grace period: one-shot admin alert + manual config purge."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import User, UserReminderLog, VpnConfig
from app.services.admin_notify import admin_notify_service
from app.services.app_setting_store import _get_setting, _set_setting
from app.services.config_provisioning import deprovision_config

SETTING_GRACE_MONTHS = "inactive_user_grace_period_months"
ALLOWED_MONTHS = frozenset({0, 1, 2, 3, 6, 12})


def get_grace_months(db: Session) -> int:
    raw = _get_setting(db, SETTING_GRACE_MONTHS, "0").strip()
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value in ALLOWED_MONTHS else 0


def set_grace_months(db: Session, months: int) -> int:
    if months not in ALLOWED_MONTHS:
        raise ValueError("grace months must be one of 0,1,2,3,6,12")
    _set_setting(db, SETTING_GRACE_MONTHS, str(months))
    db.flush()
    return months


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def scan_grace_period_alerts(db: Session) -> dict:
    months = get_grace_months(db)
    if months <= 0:
        return {"alerted": 0}
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=30 * months)
    alerted = 0
    users = db.query(User).filter(User.access_until.isnot(None)).all()
    for user in users:
        until = _as_utc(user.access_until)
        if until is None or until > threshold:
            continue
        dedup = f"grace:{until.isoformat()}"
        existing = (
            db.query(UserReminderLog)
            .filter(
                UserReminderLog.user_id == user.id,
                UserReminderLog.reminder_type == "grace_cleanup",
                UserReminderLog.dedup_key == dedup,
            )
            .first()
        )
        if existing:
            continue
        message = f"{user.username}: доступ истёк {months} мес. назад — удалить конфиги?"
        admin_notify_service.send(
            db,
            event_type="user_grace_cleanup",
            target_name=user.username,
            details=message,
        )
        db.add(
            UserReminderLog(
                user_id=user.id,
                reminder_type="grace_cleanup",
                dedup_key=dedup,
            )
        )
        db.commit()
        alerted += 1
    return {"alerted": alerted}


def run_grace_cleanup(db: Session, user: User, *, actor: User) -> dict:
    configs = (
        db.query(VpnConfig)
        .filter(VpnConfig.owner_id == user.id, VpnConfig.ha_primary_config_id.is_(None))
        .all()
    )
    deleted = 0
    for config in list(configs):
        deprovision_config(db, config=config, actor=actor, notify=False)
        deleted += 1
    if user.client_base_name:
        user.provision_state = "pending"
    db.commit()
    return {"deleted": deleted}
