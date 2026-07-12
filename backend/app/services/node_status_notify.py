"""Notify admins when a node stays offline longer than the configured grace period."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AppSetting, Node, NodeStatus
from app.services.action_log import log_action
from app.services.admin_notify import admin_notify_service

logger = logging.getLogger(__name__)

GRACE_SETTING_KEY = "node_offline_notify_grace_seconds"
DEFAULT_GRACE_SECONDS = 180
MIN_GRACE_SECONDS = 60
MAX_GRACE_SECONDS = 86400
ALERT_SENT_META_KEY = "tg_offline_alert_sent"
OFFLINE_SINCE_META_KEY = "offline_since"


def clamp_grace_seconds(value: int | float | str | None) -> int:
    try:
        seconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_GRACE_SECONDS
    return max(MIN_GRACE_SECONDS, min(MAX_GRACE_SECONDS, seconds))


def get_node_offline_grace_seconds(db: Session) -> int:
    row = db.query(AppSetting).filter(AppSetting.key == GRACE_SETTING_KEY).first()
    if not row or row.value is None or str(row.value).strip() == "":
        return DEFAULT_GRACE_SECONDS
    return clamp_grace_seconds(row.value)


def set_node_offline_grace_seconds(db: Session, seconds: int) -> int:
    value = str(clamp_grace_seconds(seconds))
    row = db.query(AppSetting).filter(AppSetting.key == GRACE_SETTING_KEY).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=GRACE_SETTING_KEY, value=value))
    return int(value)


def _host_label(node: Node) -> str:
    host = (node.host or "").strip() or "—"
    port = node.port
    if port:
        return f"{host}:{port}"
    return host


def _meta(node: Node) -> dict:
    try:
        data = json.loads(node.node_metadata or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_meta(db: Session, node: Node, meta: dict) -> None:
    node.node_metadata = json.dumps(meta)
    db.add(node)
    db.commit()
    db.refresh(node)


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _format_duration(seconds: float) -> str:
    secs = max(0, int(seconds))
    if secs < 60:
        return f"{secs} с"
    mins, rem = divmod(secs, 60)
    if rem:
        return f"{mins} мин {rem} с"
    return f"{mins} мин"


def _ensure_offline_since(db: Session, node: Node, *, now: datetime) -> dict:
    meta = _meta(node)
    if meta.get(OFFLINE_SINCE_META_KEY):
        return meta
    last_seen = _aware(node.last_seen_at)
    if last_seen is not None:
        meta[OFFLINE_SINCE_META_KEY] = last_seen.isoformat()
    else:
        meta[OFFLINE_SINCE_META_KEY] = now.isoformat()
    _save_meta(db, node, meta)
    return _meta(node)


def _offline_seconds(node: Node, now: datetime) -> float:
    meta = _meta(node)
    anchor = _parse_iso(meta.get(OFFLINE_SINCE_META_KEY) if isinstance(meta.get(OFFLINE_SINCE_META_KEY), str) else None)
    if anchor is None:
        anchor = _aware(node.last_seen_at)
    if anchor is None:
        return 0.0
    return float(max(0, int((now - anchor).total_seconds())))


def _transition_details(
    node: Node,
    *,
    error: str | None = None,
    offline_seconds: float | None = None,
    grace_seconds: int | None = None,
) -> str:
    parts = [
        f"node_id={node.id}",
        f"name={node.name}",
        f"host={_host_label(node)}",
    ]
    if offline_seconds is not None:
        parts.append(f"offline_for={_format_duration(offline_seconds)}")
    if grace_seconds is not None:
        parts.append(f"grace={_format_duration(grace_seconds)}")
    if error:
        parts.append(f"error={error}")
    return "\n".join(parts)


def _notify_details(
    *,
    error: str | None,
    offline_seconds: float,
    grace_seconds: int,
    host: str,
) -> str:
    lines = [
        f"Offline {_format_duration(offline_seconds)} (порог {_format_duration(grace_seconds)})",
        f"Хост: {host}",
    ]
    if error:
        lines.append(error)
    return "\n".join(lines)


def _handle_online(db: Session, node: Node) -> None:
    meta = _meta(node)
    was_sent = bool(meta.get(ALERT_SENT_META_KEY))
    changed = False
    if ALERT_SENT_META_KEY in meta:
        meta.pop(ALERT_SENT_META_KEY, None)
        changed = True
    if OFFLINE_SINCE_META_KEY in meta:
        meta.pop(OFFLINE_SINCE_META_KEY, None)
        changed = True
    if changed:
        _save_meta(db, node, meta)
    if not was_sent:
        return
    details = _transition_details(node)
    log_action(db, action="node_online", username="system", details=details)
    admin_notify_service.send_node_online(
        db,
        node_id=node.id,
        node_name=node.name,
        details=f"Хост: {_host_label(node)}",
    )


def _handle_offline(db: Session, node: Node, *, error: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    meta = _ensure_offline_since(db, node, now=now)
    if meta.get(ALERT_SENT_META_KEY):
        return
    grace = get_node_offline_grace_seconds(db)
    offline_sec = _offline_seconds(node, now)
    if offline_sec < grace:
        return
    meta = _meta(node)
    meta[ALERT_SENT_META_KEY] = True
    _save_meta(db, node, meta)
    details = _transition_details(
        node,
        error=error,
        offline_seconds=offline_sec,
        grace_seconds=grace,
    )
    log_action(db, action="node_offline", username="system", details=details)
    admin_notify_service.send_node_offline(
        db,
        node_id=node.id,
        node_name=node.name,
        details=_notify_details(
            error=error,
            offline_seconds=offline_sec,
            grace_seconds=grace,
            host=_host_label(node),
        ),
    )


def evaluate_node_offline_notify(
    db: Session,
    node: Node,
    *,
    prev_status: NodeStatus | None = None,
    new_status: NodeStatus | None = None,
    error: str | None = None,
) -> None:
    """Evaluate sustained offline / recovery alerts after each health update.

    ``prev_status`` is accepted for call-site compatibility; grace uses duration, not the edge alone.
    """
    del prev_status  # duration-based; kept for callers
    status = new_status if new_status is not None else node.status
    try:
        if status == NodeStatus.online:
            _handle_online(db, node)
            return
        if status == NodeStatus.offline:
            _handle_offline(db, node, error=error)
    except Exception as exc:
        logger.warning(
            "Node status notify failed for node_id=%s: %s",
            getattr(node, "id", None),
            exc,
        )


# Backwards-compatible alias used by older tests / imports
notify_node_status_transition = evaluate_node_offline_notify
