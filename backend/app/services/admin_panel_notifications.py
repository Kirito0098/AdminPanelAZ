"""Header notification center: bell writer and event_type -> category mapping.

One row is written per :meth:`AdminNotifyService.send` call, before the Telegram
gates, so the bell stays always-on even when the Telegram module is off. A writer
failure is logged and never blocks Telegram delivery.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models import AdminPanelNotification, BackgroundTask, User, UserAccessRequest

logger = logging.getLogger(__name__)

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
    "config_create": "tasks",
    "config_delete": "tasks",
    "user_create": "tasks",
    "user_delete": "tasks",
    "client_ban": "tasks",
    "user_provision_summary": "tasks",
    "access_request_new": "requests",
    "access_request_add_config": "requests",
    "access_request_extend": "requests",
    "access_request_delivery_failed": "requests",
}


def category_for_event(event_type: str) -> str:
    """Map an ``event_type`` to a bell tab category (default ``tasks``)."""
    return EVENT_CATEGORY.get(event_type, "tasks")


def write_admin_panel_notification(
    db: Session,
    *,
    event_type: str,
    title: str,
    message: str = "",
    level: str = "info",
    action_payload: dict[str, Any] | None = None,
) -> AdminPanelNotification | None:
    """Store one notification row. Never raises; returns None on DB failure."""
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


def list_notifications_for_admin(
    db: Session,
    admin: User,
    *,
    category: str | None = None,
    limit: int = 50,
    before_id: int | None = None,
) -> tuple[list[dict[str, object]], int]:
    """Список уведомлений админа (id DESC) и число непрочитанных.

    Непрочитанное: ``id > coalesce(last_read_notification_id, 0)`` — считается
    отдельно для каждого админа по его ``last_read_notification_id``.
    """
    limit = max(1, min(int(limit), 100))
    query = db.query(AdminPanelNotification).order_by(desc(AdminPanelNotification.id))
    if category:
        query = query.filter(AdminPanelNotification.category == category)
    if before_id is not None:
        query = query.filter(AdminPanelNotification.id < before_id)
    rows = query.limit(limit).all()

    last_read = admin.last_read_notification_id or 0
    unread_query = db.query(AdminPanelNotification).filter(
        AdminPanelNotification.id > last_read
    )
    if category:
        unread_query = unread_query.filter(AdminPanelNotification.category == category)
    unread_count = unread_query.count()

    items = [
        {
            "id": row.id,
            "category": row.category,
            "level": row.level,
            "event_type": row.event_type,
            "title": row.title,
            "message": row.message,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        for row in rows
    ]
    return items, unread_count


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
