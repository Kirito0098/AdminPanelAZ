"""Header notification center: bell writer and event_type -> category mapping.

One row is written per :meth:`AdminNotifyService.send` call, before the Telegram
gates, so the bell stays always-on even when the Telegram module is off. A writer
failure is logged and never blocks Telegram delivery.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models import (
    AdminPanelNotification,
    AdminPanelNotificationState,
    BackgroundTask,
    User,
    UserAccessRequest,
    UserRole,
)

logger = logging.getLogger(__name__)

# Человеческий заголовок в колокольчике: event_type видит только разработчик.
BELL_TITLES: dict[str, str] = {
    "login_success": "Вход в панель",
    "login_failed": "Неудачный вход",
    "tg_unlinked": "Telegram отвязан",
    "tg_login_unlinked": "Вход через Telegram отвязан",
    "tg_mini_login_unlinked": "Mini App: Telegram отвязан",
    "node_offline": "Узел недоступен",
    "node_online": "Узел снова в сети",
    "node_sync_drift": "HA: расхождение узлов",
    "cidr_deploy_failed": "CIDR: ошибка развёртывания",
    "cidr_ingest_partial": "CIDR: частичная загрузка",
    "cidr_rollback_failed": "CIDR: ошибка отката",
    "high_cpu": "Высокая нагрузка CPU",
    "high_ram": "Высокое потребление RAM",
    "traffic_limit": "Лимит трафика",
    "settings_change": "Изменены настройки",
    "alert_rule": "Сработало правило алерта",
    "openvpn_buffer_guard_triggered": "OpenVPN: перегрузка буфера",
    "noc_report": "NOC-отчёт",
    "config_create": "Создан конфиг",
    "config_delete": "Удалён конфиг",
    "user_create": "Создан пользователь",
    "user_delete": "Удалён пользователь",
    "client_ban": "Клиент заблокирован",
    "user_provision_summary": "Итог выдачи конфигов",
    "user_provision_applied": "Выдача конфигов",
    "openvpn_buffer_guard": "OpenVPN: перегрузка буфера",
    "panel_update_available": "Вышло обновление панели",
    "access_request_new_user": "Заявка: новый пользователь",
    "access_request_add_config": "Заявка: новый конфиг",
    "access_request_extend_access": "Заявка: продление доступа",
    "access_request_delivery_failed": "Заявка: не удалось доставить",
    "unlock_redeem": "Абонент активировал ключ",
}

# Подписи для технических ключей из details, чтобы не показывать сырой JSON.
DETAIL_LABELS: dict[str, str] = {
    "group_id": "Группа",
    "name": "Группа",
    "shared_domain": "Домен",
    "summary": "Расхождения",
    "hint": "Что сделать",
    "username": "Пользователь",
    "role": "Роль",
    "preset": "Пресет",
    "template": "Шаблон",
    "target": "Объект",
    "created": "Создано",
    "deleted": "Удалено",
    "node": "Узел",
    "node_name": "Узел",
    "profile": "Профиль",
    "client": "Клиент",
    "client_name": "Клиент",
    "error": "Ошибка",
    "reason": "Причина",
    "days": "Дней",
    "count": "Количество",
    "value": "Значение",
    "key": "Параметр",
}

_KEY_VALUE_RE = re.compile(r"(\w+)=([^,\s]+)")


def parse_bell_details(message: str | None) -> list[dict[str, str]]:
    """«Кто: Claymore · Объект: ivan · Узел: Test_serv» → пары подпись/значение.

    Формат пишут два места: ``humanize_bell_message`` и ``AdminNotifyService``
    («Кто: …»). Части без «подпись: значение» (например, свободный хвост
    «· Последний ответ 4 мин назад») отбрасываются, чтобы клиент не гадал.
    """
    details: list[dict[str, str]] = []
    for part in (message or "").split(" · "):
        label, separator, value = part.partition(": ")
        if not separator:
            continue
        label, value = label.strip(), value.strip()
        if label and value:
            details.append({"label": label, "value": value})
    return details


def bell_title(event_type: str) -> str:
    """Human title for the bell; unknown events become a readable phrase."""
    known = BELL_TITLES.get(event_type)
    if known:
        return known
    return event_type.replace("_", " ").strip().capitalize() or event_type


def _detail_label(key: str) -> str:
    return DETAIL_LABELS.get(key) or key.replace("_", " ").capitalize()


def _detail_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def humanize_bell_message(details: str | None, *, max_len: int = 2000) -> str:
    """``details`` (JSON or ``key=value``) → короткие читаемые «Подпись: значение»."""
    text = (details or "").strip()
    if not text:
        return ""
    parsed: Any = None
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        parts = [
            f"{_detail_label(str(key))}: {_detail_value(value)}"
            for key, value in parsed.items()
            if value not in (None, "", [], {})
        ]
        text = " · ".join(parts)
    elif isinstance(parsed, list):
        text = ", ".join(_detail_value(item) for item in parsed[:5])
    else:
        text = _KEY_VALUE_RE.sub(
            lambda match: f"{_detail_label(match.group(1))}: {match.group(2)}", text
        )
    return text[:max_len]


EVENT_CATEGORY: dict[str, str] = {
    "login_success": "security",
    "login_failed": "security",
    "tg_unlinked": "security",
    "tg_login_unlinked": "security",
    "tg_mini_login_unlinked": "security",
    "node_offline": "nodes",
    "node_online": "nodes",
    "node_sync_drift": "nodes",
    "cidr_deploy_failed": "services",
    "cidr_ingest_partial": "services",
    "cidr_rollback_failed": "services",
    "high_cpu": "services",
    "high_ram": "services",
    "traffic_limit": "services",
    "settings_change": "services",
    "alert_rule": "services",
    "openvpn_buffer_guard_triggered": "services",
    "noc_report": "services",
    "panel_update_available": "services",
    "config_create": "tasks",
    "config_delete": "tasks",
    "user_create": "tasks",
    "user_delete": "tasks",
    "client_ban": "tasks",
    "user_provision_summary": "tasks",
    "user_provision_applied": "tasks",
    "openvpn_buffer_guard": "services",
    "access_request_new_user": "requests",
    "access_request_add_config": "requests",
    "access_request_extend_access": "requests",
    "user_message": "requests",
    "access_request_delivery_failed": "requests",
    "unlock_redeem": "requests",
}


def category_for_event(event_type: str) -> str:
    """Map an ``event_type`` to a bell tab category (default ``tasks``)."""
    if event_type.startswith("access_request_"):
        return "requests"
    return EVENT_CATEGORY.get(event_type, "tasks")


def write_admin_panel_notification(
    db: Session,
    *,
    event_type: str,
    title: str,
    message: str = "",
    level: str = "info",
    action_payload: dict[str, Any] | None = None,
    read_for_username: str | None = None,
) -> AdminPanelNotification | None:
    """Store one notification row. Never raises; returns None on DB failure.

    ``read_for_username`` — автор действия: строка пишется для всех админов, но у него
    сразу помечена прочитанной, и в той же транзакции, чтобы SSE-поток не успел отдать
    её как новую.
    """
    try:
        row = AdminPanelNotification(
            category=category_for_event(event_type),
            level=level,
            event_type=event_type,
            title=(title or event_type)[:200],
            message=message or "",
            action_payload=json.dumps(action_payload, ensure_ascii=False)
            if action_payload
            else None,
        )
        db.add(row)
        db.flush()
        if read_for_username:
            author = db.query(User).filter(User.username == read_for_username).first()
            if author is not None and author.role == UserRole.admin:
                db.add(
                    AdminPanelNotificationState(
                        user_id=author.id,
                        notification_id=row.id,
                        read_at=datetime.utcnow(),
                    )
                )
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        logger.warning("admin panel notification write failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


_UNSET: Any = object()
SEARCH_WINDOW = 2000


def _iso_utc(value: datetime | None) -> str | None:
    """Наивный UTC из БД → ISO с явной зоной, чтобы клиент не считал его локальным."""
    return value.isoformat() + "Z" if value else None


def is_unread(
    notification_id: int,
    last_read: int,
    state: AdminPanelNotificationState | None,
    now: datetime,
) -> bool:
    """Единственное место, где решается «непрочитано» — им пользуются лента и счётчики."""
    if notification_id <= last_read:
        return False
    if state is None:
        return True
    if state.read_at is not None or state.hidden_at is not None:
        return False
    return state.snoozed_until is None or state.snoozed_until <= now


def _states_by_notification(
    db: Session, admin_id: int, notification_ids: list[int] | None = None
) -> dict[int, AdminPanelNotificationState]:
    query = db.query(AdminPanelNotificationState).filter(
        AdminPanelNotificationState.user_id == admin_id
    )
    if notification_ids is not None:
        if not notification_ids:
            return {}
        query = query.filter(AdminPanelNotificationState.notification_id.in_(notification_ids))
    return {row.notification_id: row for row in query.all()}


def _state_payload(state: AdminPanelNotificationState | None) -> dict[str, object]:
    return {
        "read": bool(state and state.read_at),
        "hidden": bool(state and state.hidden_at),
        "snoozed_until": _iso_utc(state.snoozed_until) if state else None,
    }


def _payload(raw: str | None) -> dict[str, object] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def set_notification_state(
    db: Session,
    admin: User,
    notification_id: int,
    *,
    read: bool | None = None,
    hidden: bool | None = None,
    snoozed_until: Any = _UNSET,
) -> dict[str, object] | None:
    """Проставить личное состояние уведомления. ``None`` — уведомления с таким id нет."""
    row = (
        db.query(AdminPanelNotification.id)
        .filter(AdminPanelNotification.id == notification_id)
        .one_or_none()
    )
    if row is None:
        return None
    state = (
        db.query(AdminPanelNotificationState)
        .filter(
            AdminPanelNotificationState.user_id == admin.id,
            AdminPanelNotificationState.notification_id == notification_id,
        )
        .one_or_none()
    )
    if state is None:
        state = AdminPanelNotificationState(user_id=admin.id, notification_id=notification_id)
        db.add(state)
    now = datetime.utcnow()
    if read is not None:
        state.read_at = now if read else None
    if hidden is not None:
        state.hidden_at = now if hidden else None
    if snoozed_until is not _UNSET:
        state.snoozed_until = snoozed_until
    db.commit()
    db.refresh(state)
    return _state_payload(state)


def enabled_bell_categories(user: User) -> set[str]:
    """Категории, которые админ разрешил показывать в колокольчике и ленте."""
    return {key for key, enabled in user.bell_categories().items() if enabled}


def _notification_counts(
    db: Session, admin: User, last_read: int, now: datetime
) -> dict[str, object]:
    """Счётчики по всем уведомлениям админа: чипы категорий, бейдж, «требует внимания»."""
    enabled = enabled_bell_categories(admin)
    rows = (
        db.query(
            AdminPanelNotification.id,
            AdminPanelNotification.category,
            AdminPanelNotification.level,
        )
        .filter(AdminPanelNotification.category.in_(sorted(enabled)))
        .all()
    )
    states = _states_by_notification(db, admin.id)
    by_category: dict[str, dict[str, int]] = {}
    unread = attention = snoozed = hidden = 0
    for row in rows:
        state = states.get(row.id)
        bucket = by_category.setdefault(row.category, {"total": 0, "unread": 0})
        bucket["total"] += 1
        if state is not None and state.hidden_at is not None:
            hidden += 1
        if state is not None and state.snoozed_until and state.snoozed_until > now:
            snoozed += 1
        if is_unread(row.id, last_read, state, now):
            unread += 1
            bucket["unread"] += 1
            if row.level == "error":
                attention += 1
    return {
        "unread": unread,
        "attention": attention,
        "snoozed": snoozed,
        "hidden": hidden,
        "by_category": by_category,
    }


def list_notifications_for_admin(
    db: Session,
    admin: User,
    *,
    category: str | None = None,
    level: str | None = None,
    unread_only: bool = False,
    q: str | None = None,
    hidden_only: bool = False,
    before_id: int | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, object]], int, dict[str, object]]:
    """Лента админа: items (id DESC), число непрочитанных и счётчики по категориям.

    Скрытые уведомления в ленту не попадают, если не запрошены явно (``hidden_only``).
    Поиск идёт в Python: ``LIKE`` в SQLite не сворачивает регистр кириллицы.
    """
    limit = max(1, min(int(limit), 100))
    now = datetime.utcnow()
    last_read = admin.last_read_notification_id or 0
    enabled = enabled_bell_categories(admin)

    query = (
        db.query(AdminPanelNotification)
        .filter(AdminPanelNotification.category.in_(sorted(enabled)))
        .order_by(desc(AdminPanelNotification.id))
    )
    if category:
        query = query.filter(AdminPanelNotification.category == category)
    if level:
        query = query.filter(AdminPanelNotification.level == level)
    if before_id is not None:
        query = query.filter(AdminPanelNotification.id < before_id)
    if unread_only:
        # Непрочитанное всегда новее водяного знака (см. is_unread) — узкий префильтр,
        # чтобы расширенное окно ниже не тянуло всю прочитанную ленту.
        query = query.filter(AdminPanelNotification.id > last_read)

    needle = (q or "").strip().casefold()
    # unread_only и поиск отсеиваются в Python, поэтому окно шире страницы: иначе верхние
    # прочитанные съедают слоты и страница возвращается короче запрошенной.
    rows = query.limit(SEARCH_WINDOW if (needle or unread_only) else limit).all()
    states = _states_by_notification(db, admin.id, [row.id for row in rows])

    items: list[dict[str, object]] = []
    for row in rows:
        state = states.get(row.id)
        if bool(state is not None and state.hidden_at is not None) != hidden_only:
            continue
        if unread_only and not is_unread(row.id, last_read, state, now):
            continue
        if needle and needle not in f"{row.title or ''} {row.message or ''}".casefold():
            continue
        state_payload = _state_payload(state)
        if row.id <= last_read:
            # Водяной знак — тоже прочтение; без этого карточка выглядит непрочитанной,
            # хотя бейдж и счётчики считают её прочитанной.
            state_payload["read"] = True
        items.append(
            {
                "id": row.id,
                "category": row.category,
                "level": row.level,
                "event_type": row.event_type,
                "title": row.title,
                "message": row.message,
                "created_at": _iso_utc(row.created_at) or "",
                "action_payload": _payload(row.action_payload),
                "details": parse_bell_details(row.message),
                "state": state_payload,
            }
        )
        if len(items) >= limit:
            break

    counts = _notification_counts(db, admin, last_read, now)
    return items, int(counts["unread"]), counts


def mark_notifications_read(db: Session, admin: User, up_to_id: int) -> None:
    """last_read = max(existing or 0, up_to_id). Только растёт, никогда не откатывается."""
    if up_to_id < 1:
        return
    current = admin.last_read_notification_id or 0
    admin.last_read_notification_id = max(current, int(up_to_id))
    db.add(admin)
    db.commit()


def notifications_stream_snapshot(db: Session) -> dict:
    """Снимок состояния для SSE-потока: верхнее id уведомлений, заявки, задачи."""
    max_n = db.query(func.max(AdminPanelNotification.id)).scalar() or 0
    pending = [
        int(r[0])
        for r in (
            db.query(UserAccessRequest.id)
            .filter(UserAccessRequest.status == "pending")
            .order_by(desc(UserAccessRequest.id))
            .limit(20)
            .all()
        )
    ]
    tasks = (
        db.query(BackgroundTask)
        .filter(BackgroundTask.task_type == "user_provision")
        .filter(BackgroundTask.status.in_(("pending", "running")))
        .all()
    )
    return {
        "max_notification_id": int(max_n),
        "pending_request_ids": pending,
        "tasks": [
            {
                "id": t.id,
                "subject_key": t.subject_key,
                "progress": t.progress_percent,
                "status": t.status,
            }
            for t in tasks
        ],
    }
