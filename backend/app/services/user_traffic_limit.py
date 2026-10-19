"""Per-user traffic accounting and enforcement on top of ``get_client_consumed_traffic_bytes``.

Считает потреблённый пользователем трафик с момента ``User.traffic_counter_reset_at``
по всем его конфигам на всех узлах (включая HA-тени с тем же ``client_name``).
Без ``traffic_limit_bytes`` или без ``traffic_counter_reset_at`` — ноль.

Enforcement (`reconcile_user_traffic_limits`) вешает / снимает sticky блок
``user_traffic_limit`` и шлёт напоминания 80/95% один раз на счётный период.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import User, VpnConfig
from app.services.admin_notify import admin_notify_service
from app.services.app_setting_store import _get_setting
from app.services.feature_guards import get_feature_service
from app.services.self_service import record_reminder_sent, reminder_recently_sent
from app.services.telegram import send_tg_message
from app.services.traffic_limit import get_client_consumed_traffic_bytes, human_bytes
from app.services.user_blocks import apply_user_block, lift_user_block

logger = logging.getLogger(__name__)

REMINDER_USER_TRAFFIC = "user_traffic_limit"
TRAFFIC_REMINDER_PCT = (80, 95)


def _owned_config_names(db: Session, user_id: int) -> list[str]:
    """Уникальные имена owned-конфигов пользователя (без HA-теневиков по primary_config_id)."""
    names: set[str] = set()
    for config in (
        db.query(VpnConfig)
        .filter(VpnConfig.owner_id == user_id, VpnConfig.ha_primary_config_id.is_(None))
        .all()
    ):
        name = (config.client_name or "").strip()
        if name:
            names.add(name)
    return sorted(names)


def user_consumed_bytes(db: Session, user: User) -> int:
    """Байт, потребил пользователь с ``traffic_counter_reset_at`` по все узлы.

    Суммируется по уникальным именам — конфиг с одинаковым именем на первичном узле и на
    его HA-реплике учитывается один раз (запрос по имени без фильтра node_id уже охватывает
    все узлы для этого имени).
    """
    if not user.traffic_limit_bytes or not user.traffic_counter_reset_at:
        return 0
    since = user.traffic_counter_reset_at
    total = 0
    for name in _owned_config_names(db, user.id):
        total += get_client_consumed_traffic_bytes(db, client_name=name, since=since)
    return total


def _tg_text_exhausted(limit: int) -> str:
    return f"Лимит трафика {human_bytes(limit)} исчерпан. Доступ откроется после продления."


def _tg_text_cleared() -> str:
    return "Доступ снова открыт."


def _tg_text_reminder(pct: int, consumed: int, limit: int) -> str:
    consumed_h = human_bytes(consumed)
    limit_h = human_bytes(limit)
    if pct >= 95:
        return f"Лимит трафика почти исчерпан: {consumed_h or '—'} из {limit_h or '—'}."
    return f"Использовано {consumed_h or '—'} из {limit_h or '—'} ({pct}%) — скоро может исчерпаться лимит трафика."


def _notify_owner(db: Session, user: User, text: str) -> None:
    if not user.telegram_id:
        return
    bot_token = _get_setting(db, "telegram_bot_token")
    if bot_token:
        send_tg_message(bot_token, str(user.telegram_id), text)


def _notify_limit_exhausted(db: Session, user: User, limit: int) -> None:
    _notify_owner(db, user, _tg_text_exhausted(limit))
    try:
        admin_notify_service.send(
            db,
            event_type="traffic_limit",
            actor_username="user_traffic_limit",
            target_name=user.username,
            details=f"user_traffic_limit exceeded limit={human_bytes(limit)}",
        )
    except Exception:  # уведомление не должно ломать enforce
        logger.exception("admin notify traffic limit exhausted failed user_id=%s", user.id)


def _notify_limit_cleared(db: Session, user: User) -> None:
    _notify_owner(db, user, _tg_text_cleared())


def _lift_all_user_traffic_blocks(db: Session) -> int:
    """Снять user_traffic_limit со всех пользователей (например, выключили traffic_sync)."""
    lifted = 0
    for user in db.query(User).filter(User.traffic_limit_blocked.is_(True)).all():
        user.traffic_limit_blocked = False
        db.add(user)
        lift_user_block(db, user, "user_traffic_limit", actor="traffic_sync_off")
        lifted += 1
    db.commit()
    return lifted


def reconcile_user_traffic_limits(db: Session) -> dict:
    """Для каждого пользователя с лимитом: блок/разблок user_traffic_limit, напоминания 80/95.

    Если модуль сбора трафика выключен — снимает все user_traffic_limit блоки.
    """
    if not get_feature_service().is_enabled("traffic_sync"):
        return {
            "blocked": 0,
            "unblocked": _lift_all_user_traffic_blocks(db),
            "reminded": 0,
        }

    blocked = unblocked = reminded = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    users = db.query(User).filter(User.traffic_limit_bytes.isnot(None)).all()
    for user in users:
        if user.traffic_counter_reset_at is None:
            user.traffic_counter_reset_at = now
            db.add(user)
            db.flush()
        consumed = user_consumed_bytes(db, user)
        limit = int(user.traffic_limit_bytes or 0)
        for pct in TRAFFIC_REMINDER_PCT:
            if limit > 0 and consumed >= limit * pct // 100:
                key = f"{user.traffic_counter_reset_at.isoformat()}:{pct}"
                if not reminder_recently_sent(db, user.id, REMINDER_USER_TRAFFIC, key):
                    _notify_owner(db, user, _tg_text_reminder(pct, consumed, limit))
                    record_reminder_sent(db, user.id, REMINDER_USER_TRAFFIC, key)
                    reminded += 1
        if consumed >= limit and not user.traffic_limit_blocked:
            if user.suspended_at is None:  # suspend outranks traffic
                apply_user_block(db, user, "user_traffic_limit", actor="user_traffic_limit")
            user.traffic_limit_blocked = True
            db.commit()
            _notify_limit_exhausted(db, user, limit)
            blocked += 1
        elif consumed < limit and user.traffic_limit_blocked:
            user.traffic_limit_blocked = False
            db.commit()
            lift_user_block(db, user, "user_traffic_limit", actor="user_traffic_limit")
            if user.suspended_at is not None:
                apply_user_block(db, user, "user_suspended", actor="user_traffic_limit")
            _notify_limit_cleared(db, user)
            unblocked += 1
    return {"blocked": blocked, "unblocked": unblocked, "reminded": reminded}


def reset_user_traffic_counter(
    db: Session, user: User, *, actor: str, check_now: bool = True
) -> User:
    """Сбросить счётчик пользователя и снять его блок user_traffic_limit."""
    _ = check_now  # сохранено для совместимости вызова; после сброса окна пусто
    user.traffic_counter_reset_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if user.traffic_limit_blocked:
        user.traffic_limit_blocked = False
        db.add(user)
        db.flush()
        lift_user_block(db, user, "user_traffic_limit", actor=actor)
    db.commit()
    db.refresh(user)
    return user
