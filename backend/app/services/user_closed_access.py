"""Closed-access view for the user portal and the Mini App (Stage 3, Task 11).

Spec 7.4: while access is closed the person sees the reason on top, configs
stay listed and downloads stay available.

States (in priority order):
- ``suspended``     — admin suspend (``user_suspended``)
- ``traffic_limit`` — per-user traffic limit exhausted (``user_traffic_limit``)
- ``expired``      — ``access_until`` is in the past
- ``expiring``     — ``access_until`` within the next 7 days (amber, not closed yet)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import User

# Окно предупреждения об истечении (amber-баннер «Доступ до DD.MM»).
EXPIRING_WINDOW_DAYS = 7
# Месяц в grace-периоде считается как 30 дней (тот же ориентир, что в user_grace).
MONTH_DAYS = 30


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def closed_access_view(user: User, now: datetime | None = None) -> dict | None:
    """Состояние закрытого доступа пользователя или ``None`` (доступ открыт).

    Возвращает ``{"state", "reason", "access_until"}``:
    - ``state`` — suspended | traffic_limit | expired | expiring
    - ``reason`` — причина приостановки (только если админ разрешил её показывать)
    - ``access_until`` — ISO-дата срока доступа (для expired/expiring)
    """
    current = _as_utc(now) or _now()
    if user.suspended_at is not None:
        return {
            "state": "suspended",
            "reason": user.suspend_reason if user.suspend_reason_visible else None,
            "access_until": None,
        }
    if user.traffic_limit_blocked:
        return {"state": "traffic_limit", "reason": None, "access_until": None}
    until = _as_utc(user.access_until)
    if until is not None and until <= current:
        return {"state": "expired", "reason": None, "access_until": until.isoformat()}
    if until is not None and until <= current + timedelta(days=EXPIRING_WINDOW_DAYS):
        return {"state": "expiring", "reason": None, "access_until": until.isoformat()}
    return None


def grace_hold_view(
    user: User, grace_months: int, now: datetime | None = None
) -> dict | None:
    """Удержание по истечении срока: ``{"elapsed_months", "limit_months"}`` или ``None``.

    Показывается в шапке карточки абонента: «Истёк: удержание N из M мес.».
    """
    if grace_months <= 0:
        return None
    current = _as_utc(now) or _now()
    until = _as_utc(user.access_until)
    if until is None or until > current:
        return None
    elapsed_days = (current - until).days
    elapsed_months = elapsed_days // MONTH_DAYS
    if elapsed_months <= 0:
        return None
    return {"elapsed_months": int(elapsed_months), "limit_months": int(grace_months)}


def _requests_enabled(db: Session) -> bool:
    """Stage 2: приём заявок на продление включён? (кнопка «Запросить продление»)."""
    from app.services.app_setting_store import _get_setting

    return _get_setting(db, "telegram_accept_access_requests", "false") == "true"


def _admin_contact_url(db: Session) -> str | None:
    """Ссылка на бота для «Написать администратору» (если бот настроен)."""
    from app.services.app_setting_store import _get_setting

    username = (_get_setting(db, "telegram_bot_username", "") or "").strip().lstrip("@")
    if not username:
        return None
    return f"https://t.me/{username}"


def closed_access_payload(db: Session, user: User, now: datetime | None = None) -> dict | None:
    """Закрытый доступ + доступные действия (для портала и Mini App)."""
    view = closed_access_view(user, now)
    if view is None:
        return None
    view["requests_enabled"] = _requests_enabled(db)
    view["contact_url"] = _admin_contact_url(db)
    return view
