"""Lightweight NOC summary for scheduled Telegram reports (DB aggregates only)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AppSetting, Node, NodeStatus, TrafficSessionState, User
from app.services.feature_guards import get_feature_service
from app.services.node_compare_metrics import get_traffic_totals_by_node
from app.services.notify_time import format_notify_when
from app.services.resource_metrics import get_latest_samples_by_node
from app.services.telegram import send_tg_message
from app.services.traffic_limit import human_bytes

logger = logging.getLogger(__name__)

NOC_REPORT_EVENT = "noc_report"


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def _wg_profile(profile: str | None) -> bool:
    return "-wg" in (profile or "").lower()


def build_noc_summary(db: Session) -> dict:
    """Aggregate NOC metrics from DB without live node adapter calls."""
    nodes = db.query(Node).order_by(Node.id.asc()).all()
    latest_metrics = get_latest_samples_by_node(db)
    traffic_totals = get_traffic_totals_by_node(db)

    active_rows = (
        db.query(
            TrafficSessionState.node_id,
            TrafficSessionState.profile,
            func.count(TrafficSessionState.id),
        )
        .filter(TrafficSessionState.is_active.is_(True))
        .group_by(TrafficSessionState.node_id, TrafficSessionState.profile)
        .all()
    )

    sessions_by_node: dict[int, dict[str, int]] = {}
    total_ovpn = 0
    total_wg = 0
    for node_id, profile, count in active_rows:
        bucket = sessions_by_node.setdefault(int(node_id), {"openvpn": 0, "wireguard": 0})
        if _wg_profile(profile):
            bucket["wireguard"] += int(count or 0)
            total_wg += int(count or 0)
        else:
            bucket["openvpn"] += int(count or 0)
            total_ovpn += int(count or 0)

    node_lines: list[dict] = []
    nodes_online = 0
    total_traffic = 0
    for node in nodes:
        if node.status == NodeStatus.online:
            nodes_online += 1
        sessions = sessions_by_node.get(node.id, {"openvpn": 0, "wireguard": 0})
        sample = latest_metrics.get(node.id)
        traffic = int(traffic_totals.get(node.id) or 0)
        total_traffic += traffic
        node_lines.append(
            {
                "name": node.name,
                "status": node.status.value if hasattr(node.status, "value") else str(node.status),
                "openvpn": sessions["openvpn"],
                "wireguard": sessions["wireguard"],
                "cpu_percent": round(sample.cpu_percent, 1) if sample else None,
                "memory_percent": round(sample.memory_percent, 1) if sample else None,
                "traffic_bytes": traffic,
            }
        )

    return {
        "timestamp": datetime.now(timezone.utc),
        "nodes_total": len(nodes),
        "nodes_online": nodes_online,
        "total_openvpn": total_ovpn,
        "total_wireguard": total_wg,
        "total_traffic_bytes": total_traffic,
        "nodes": node_lines,
    }


def format_noc_report_message(summary: dict, *, period: str) -> str:
    period_label = "еженедельная" if period == "weekly" else "ежедневная"
    when = format_notify_when(None)
    lines = [
        f"📊 <b>NOC сводка ({period_label})</b>",
        f"🕐 {when}",
        "",
        f"Узлы: <b>{summary['nodes_online']}/{summary['nodes_total']}</b> online",
        (
            f"Сессии: OVPN <b>{summary['total_openvpn']}</b>"
            f" · WG <b>{summary['total_wireguard']}</b>"
        ),
    ]

    traffic_label = human_bytes(summary.get("total_traffic_bytes"))
    if traffic_label:
        lines.append(f"Трафик (всего): <b>{traffic_label}</b>")

    lines.append("")
    for node in summary.get("nodes") or []:
        status_icon = "🟢" if node.get("status") == NodeStatus.online.value else "🔴"
        parts = [
            f"OVPN {node.get('openvpn', 0)}",
            f"WG {node.get('wireguard', 0)}",
        ]
        if node.get("cpu_percent") is not None:
            parts.append(f"CPU {node['cpu_percent']}%")
        if node.get("memory_percent") is not None:
            parts.append(f"RAM {node['memory_percent']}%")
        lines.append(f"{status_icon} <b>{node.get('name')}</b> · {' · '.join(parts)}")

    return "\n".join(lines)


def _notify_recipients(db: Session) -> list[User]:
    return [
        user
        for user in db.query(User).filter(User.telegram_id.isnot(None)).all()
        if user.has_tg_notify_event(NOC_REPORT_EVENT)
    ]


def send_noc_report(db: Session, *, period: str) -> dict:
    """Build summary and deliver to admins with noc_report TG preference enabled."""
    if not get_feature_service().is_enabled("telegram"):
        return {"status": "skipped", "reason": "telegram_disabled"}
    if _get_setting(db, "telegram_notify_enabled", "false") != "true":
        return {"status": "skipped", "reason": "notify_disabled"}

    bot_token = _get_setting(db, "telegram_bot_token", "").strip()
    if not bot_token:
        return {"status": "skipped", "reason": "no_bot_token"}

    recipients = _notify_recipients(db)
    if not recipients:
        return {"status": "skipped", "reason": "no_recipients"}

    summary = build_noc_summary(db)
    text = format_noc_report_message(summary, period=period)
    sent = 0
    for user in recipients:
        try:
            if send_tg_message(bot_token, user.telegram_id, text):
                sent += 1
        except Exception as exc:
            logger.warning("NOC report TG send failed for user %s: %s", user.id, exc)

    return {"status": "sent", "period": period, "recipients": len(recipients), "sent": sent}
