"""Header notification center: bell writer and event_type -> category mapping.

One row is written per :meth:`AdminNotifyService.send` call, before the Telegram
gates, so the bell stays always-on even when the Telegram module is off. A writer
failure is logged and never blocks Telegram delivery.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import AdminPanelNotification

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
